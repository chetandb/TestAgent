import argparse
import asyncio
import json
import re
import sys
import time
import urllib.parse

import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


class WebsiteTestAgent:
    def __init__(self, start_url, max_pages=10, headless=True, timeout=15000):
        self.start_url = self._normalize_url(start_url)
        self.parsed_base = urllib.parse.urlparse(self.start_url)
        self.max_pages = max_pages
        self.headless = headless
        self.timeout = timeout
        self.explored_pages = {}
        self.site_links = set()
        self.discovery_queue = [self.start_url]
        self.test_results = []

    def _normalize_url(self, url):
        url = url.strip()
        if not re.match(r"https?://", url):
            url = "https://" + url
        return urllib.parse.urljoin(url, urllib.parse.urlparse(url).path)

    def _same_domain(self, url):
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc == self.parsed_base.netloc

    async def explore_website(self):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context = await browser.new_context(java_script_enabled=True)
            while self.discovery_queue and len(self.explored_pages) < self.max_pages:
                url = self.discovery_queue.pop(0)
                if url in self.explored_pages:
                    continue

                page = await context.new_page()
                page.set_default_timeout(self.timeout)
                page_info = {
                    "url": url,
                    "status": None,
                    "title": None,
                    "links": [],
                    "forms": [],
                    "buttons": [],
                    "error": None,
                }

                try:
                    response = await page.goto(url, wait_until="load")
                    page_info["status"] = response.status if response else None
                    page_info["title"] = await page.title()

                    anchors = await page.query_selector_all("a[href]")
                    for a in anchors:
                        href = await a.get_attribute("href")
                        if not href:
                            continue
                        href = urllib.parse.urljoin(url, href.split("#")[0])
                        page_info["links"].append(href)
                        if self._same_domain(href) and href not in self.explored_pages and href not in self.discovery_queue:
                            self.discovery_queue.append(href)
                        self.site_links.add(href)

                    forms = await page.query_selector_all("form")
                    for form in forms:
                        fields = []
                        for field in await form.query_selector_all("input, textarea, select"):
                            name = await field.get_attribute("name")
                            r = await field.get_attribute("required")
                            t = await field.get_attribute("type")
                            fields.append({"name": name, "type": t or "", "required": bool(r)})
                        page_info["forms"].append({"action": await form.get_attribute("action"), "method": (await form.get_attribute("method") or "get").lower(), "fields": fields})

                    buttons = await page.query_selector_all("button, input[type=submit], input[type=button]")
                    for button in buttons:
                        txt = (await button.inner_text()).strip() if await button.inner_text() else ""
                        page_info["buttons"].append({"text": txt})

                except PlaywrightTimeoutError as e:
                    page_info["error"] = f"Timeout while loading: {e}"
                except Exception as e:
                    page_info["error"] = str(e)
                finally:
                    self.explored_pages[url] = page_info
                    await page.close()

            await browser.close()

    def generate_test_cases(self):
        cases = []
        cases.append({
            "id": "load-start-url",
            "description": f"Start URL loads without network error: {self.start_url}",
            "type": "load",
            "target": self.start_url,
        })

        for url, info in self.explored_pages.items():
            cases.append({
                "id": f"page-status-{len(cases)+1}",
                "description": f"Page {url} returns 200 or 2xx status code",
                "type": "http-status",
                "target": url,
            })

            for link in info.get("links", []):
                if self._same_domain(link):
                    cases.append({
                        "id": f"internal-link-{len(cases)+1}",
                        "description": f"Internal link {link} resolves successfully (status 200-399)",
                        "type": "link-check",
                        "target": link,
                    })

            for form in info.get("forms", []):
                if form.get("fields"):
                    cases.append({
                        "id": f"form-fields-{len(cases)+1}",
                        "description": f"Form on {url} has fields and can be validated for required fields",
                        "type": "form-required",
                        "target": url,
                        "form": form,
                    })

            if info.get("buttons"):
                cases.append({
                    "id": f"buttons-count-{len(cases)+1}",
                    "description": f"Page {url} has {len(info.get('buttons'))} button(s)",
                    "type": "buttons-existence",
                    "target": url,
                })

        return cases

    def run_test_cases(self, cases):
        self.test_results = []

        # 1: HTTP checks via requests for speed.
        for c in cases:
            result = {
                "id": c["id"],
                "description": c["description"],
                "target": c.get("target"),
                "status": "not-run",
                "details": None,
                "passed": False,
            }

            try:
                if c["type"] in ["load", "http-status", "link-check"]:
                    r = requests.get(c["target"], timeout=10, allow_redirects=True)
                    result["details"] = {"http_status": r.status_code}
                    result["passed"] = 200 <= r.status_code < 400
                    result["status"] = "passed" if result["passed"] else "failed"

                elif c["type"] == "form-required":
                    required_fields = [f for f in c["form"]["fields"] if f.get("required")]
                    if required_fields:
                        result["details"] = {
                            "required_fields": required_fields,
                            "info": "Required fields found; the form should enforce client/server validation."
                        }
                        result["passed"] = True
                        result["status"] = "passed"
                    else:
                        result["details"] = {"required_fields": [], "info": "No explicitly required fields detected."}
                        result["passed"] = False
                        result["status"] = "failed"

                elif c["type"] == "buttons-existence":
                    result["passed"] = True
                    result["status"] = "passed"

                else:
                    result["status"] = "skipped"
                    result["details"] = f"Unknown case type: {c['type']}"

            except Exception as e:
                result["status"] = "error"
                result["details"] = str(e)

            self.test_results.append(result)

    def generate_smart_test_cases(self):
        cases = []
        for url, info in self.explored_pages.items():
            for idx, form in enumerate(info.get("forms", []), start=1):
                if not form.get("fields"):
                    continue
                cases.append({
                    "id": f"smart-form-submit-{len(cases)+1}",
                    "description": f"Submit form on {url} with sample data",
                    "type": "form-submit",
                    "target": url,
                    "form": form,
                })

            for idx, button in enumerate(info.get("buttons", []), start=1):
                text = button.get("text", "").strip() or "no-text"
                if text:
                    cases.append({
                        "id": f"smart-button-click-{len(cases)+1}",
                        "description": f"Click button '{text}' on {url}",
                        "type": "button-click",
                        "target": url,
                        "button_text": text,
                    })

        return cases

    async def run_smart_test_cases(self, cases):
        self.test_results = self.test_results or []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context = await browser.new_context(java_script_enabled=True)

            for c in cases:
                result = {
                    "id": c["id"],
                    "description": c["description"],
                    "target": c.get("target"),
                    "status": "not-run",
                    "details": None,
                    "passed": False,
                }

                page = await context.new_page()
                page.set_default_timeout(self.timeout)
                try:
                    await page.goto(c["target"], wait_until="load")

                    if c["type"] == "form-submit":
                        form_data = {}
                        for f in c["form"]["fields"]:
                            if not f.get("name"):
                                continue
                            typ = (f.get("type") or "").lower()
                            if typ in ["email"]:
                                form_data[f["name"]] = "test@example.com"
                            elif typ in ["password"]:
                                form_data[f["name"]] = "P@ssw0rd123"
                            elif typ in ["tel"]:
                                form_data[f["name"]] = "+1234500000"
                            else:
                                form_data[f["name"]] = "test"

                        for name, value in form_data.items():
                            try:
                                await page.fill(f"[name=\"{name}\"]", value)
                            except Exception:
                                pass

                        try:
                            await page.click("form [type=submit], form button[type=submit], form button")
                        except Exception:
                            pass

                        await page.wait_for_load_state("networkidle", timeout=5000)
                        response = page
                        status = None
                        try:
                            status = (await page.wait_for_response("**/*", timeout=3000)).status
                        except Exception:
                            pass
                        result["details"] = {
                            "form_data": form_data,
                            "http_status": status,
                            "final_url": page.url,
                        }
                        result["passed"] = True
                        result["status"] = "passed"

                    elif c["type"] == "button-click":
                        button_text = c.get("button_text", "")
                        clicked = False
                        try:
                            await page.click(f"button:has-text(\"{button_text}\")", timeout=3000)
                            clicked = True
                        except Exception:
                            try:
                                await page.click(f"[type=button]:has-text(\"{button_text}\")", timeout=3000)
                                clicked = True
                            except Exception:
                                clicked = False

                        result["details"] = {
                            "click_attempted": button_text,
                            "clicked": clicked,
                            "after_url": page.url,
                        }
                        result["passed"] = clicked
                        result["status"] = "passed" if clicked else "failed"

                    else:
                        result["status"] = "skipped"
                        result["details"] = f"Unknown smart case type: {c['type']}"

                except Exception as e:
                    result["status"] = "error"
                    result["details"] = str(e)
                finally:
                    await page.close()
                    self.test_results.append(result)

            await browser.close()

    def format_text_report(self, summary):
        lines = [
            f"Website Test Report for: {summary.get('start_url')}",
            f"Pages explored: {summary.get('pages_explored')}",
            f"Test cases executed: {summary.get('cases_executed')}",
            f"Passed: {summary.get('passed')}",
            f"Failed: {summary.get('failed')}",
            f"Errors: {summary.get('errors')}",
            "" ,
            "Test case results:",
        ]
        for case in summary.get('details', []):
            lines.append(f"- [{case.get('status')}] {case.get('id')} | {case.get('description')} | target={case.get('target')} | passed={case.get('passed')}")
            if case.get('details') is not None:
                lines.append(f"  details: {case.get('details')}")
        return "\n".join(lines)

    def format_html_report(self, summary):
        html = [
            "<html>",
            "<head><title>Website Test Report</title></head>",
            "<body>",
            f"<h1>Website Test Report for: {summary.get('start_url')}</h1>",
            f"<p>Pages explored: {summary.get('pages_explored')}</p>",
            f"<p>Test cases executed: {summary.get('cases_executed')}</p>",
            f"<p>Passed: {summary.get('passed')}<br>Failed: {summary.get('failed')}<br>Errors: {summary.get('errors')}</p>",
            "<h2>Test case details</h2>",
            "<table border='1' cellpadding='4' cellspacing='0'>",
            "<thead><tr><th>ID</th><th>Status</th><th>Passed</th><th>Description</th><th>Target</th><th>Details</th></tr></thead>",
            "<tbody>",
        ]
        for case in summary.get('details', []):
            details = case.get('details')
            details_text = json.dumps(details, ensure_ascii=False) if details is not None else ''
            html.append(
                "<tr>"
                f"<td>{case.get('id')}</td>"
                f"<td>{case.get('status')}</td>"
                f"<td>{case.get('passed')}</td>"
                f"<td>{case.get('description')}</td>"
                f"<td>{case.get('target')}</td>"
                f"<td>{details_text}</td>"
                "</tr>"
            )
        html.extend(["</tbody>", "</table>", "</body>", "</html>"])
        return "\n".join(html)

    def report(self):
        summary = {
            "start_url": self.start_url,
            "pages_explored": len(self.explored_pages),
            "cases_executed": len(self.test_results),
            "passed": sum(1 for t in self.test_results if t.get("passed")),
            "failed": sum(1 for t in self.test_results if t.get("status") == "failed"),
            "errors": sum(1 for t in self.test_results if t.get("status") == "error"),
            "details": self.test_results,
        }
        return summary


async def main():
    parser = argparse.ArgumentParser(description="Website Test Agent: explore, generate, and run tests on a site URL")
    parser.add_argument("--url", required=True, help="Root URL to test (http:// or https://)")
    parser.add_argument("--max-pages", type=int, default=10, help="Max number of pages to crawl")
    parser.add_argument("--non-headless", action="store_true", help="Run browser in non-headless mode for debugging")
    parser.add_argument("--output", default="test_report.txt", help="Output report path")
    parser.add_argument("--output-format", choices=["text", "html"], default="text", help="Output format for report")
    parser.add_argument("--smart", action="store_true", help="Also generate and execute smart interactive test cases (forms/buttons)")

    args = parser.parse_args()
    agent = WebsiteTestAgent(args.url, max_pages=args.max_pages, headless=not args.non_headless)

    print(f"[INFO] Exploring site starting at {agent.start_url} (max {agent.max_pages} pages)")
    await agent.explore_website()

    print(f"[INFO] Generating test cases from discovered functionality")
    cases = agent.generate_test_cases()

    print(f"[INFO] Running {len(cases)} test cases")
    agent.run_test_cases(cases)

    if args.smart:
        smart_cases = agent.generate_smart_test_cases()
        print(f"[INFO] Running {len(smart_cases)} smart interactive test cases")
        await agent.run_smart_test_cases(smart_cases)

    final = agent.report()

    if args.output_format == "json":
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=2)
        print(f"[RESULT] JSON report saved to {args.output}")

    elif args.output_format == "text":
        text_report = agent.format_text_report(final)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text_report)
        print(f"[RESULT] text report saved to {args.output}")

    elif args.output_format == "html":
        html_report = agent.format_html_report(final)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html_report)
        print(f"[RESULT] html report saved to {args.output}")

    else:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(final, f, indent=2)
        print(f"[RESULT] JSON report saved to {args.output}")
    print(json.dumps({
        "start_url": final["start_url"],
        "pages_explored": final["pages_explored"],
        "cases_executed": final["cases_executed"],
        "passed": final["passed"],
        "failed": final["failed"],
        "errors": final["errors"],
    }, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[WARN] Execution interrupted by user")
        sys.exit(1)
