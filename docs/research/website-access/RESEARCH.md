# MarketTwin website access and payment capabilities

Research date: September 20, 2026. Audited the local Python-browser-controller architecture, current official Playwright/Stripe/Cloudflare documentation, and local browser fixtures. Application runtime code was not changed. No external target was tested, no credentials were used, and no payment was attempted.

**Conclusion: the Python + Playwright + Chromium foundation is suitable for broad web testing, but MarketTwin cannot presently promise access to every website or complete payment-flow coverage. Public pricing inspection, authenticated billing inspection, and payment execution are separate capabilities.**

“Access” must be separated into loading a page, observing its relevant contents, interacting with its controls, and verifying a result. Success at one level does not imply success at the next. This investigation uses primary implementation documentation rather than extrapolating universal compatibility from web-agent benchmark scores.

## Current capability matrix

| Target or task | Current state | Main limitation |
|---|---|---|
| Approved public HTTP(S) pages | Supported in principle | Reachability, dependency origins, rendering and observation coverage still matter. |
| Modern JavaScript applications | Chromium can execute the application | API/CDN requests must pass policy; waits and relevant scene capture need validation. |
| Arbitrary external links or redirects | Restricted | Exact approved origin checks, including scheme and effective port. |
| Public prices, fees, billing terms | Inspectable if rendered and captured | Existing collector can omit paragraphs and later visible elements. |
| Signed-in invoices, plan details, masked saved-card labels | Technically possible after authorized authentication | Fresh sessions have no user login; end-to-end human handoff is unfinished. |
| Embedded checkout forms | Incomplete | No frame-addressed observation/action contract in the current tools. |
| Open Shadow DOM controls | Partial | Playwright semantic locators can find them; the custom visible-element collector misses them. |
| Closed Shadow DOM or canvas-only UI | Limited | Current DOM extraction cannot provide complete semantics; targeted visual support or explicit test hooks would be needed. |
| CAPTCHA/bot-protected production pages | Not guaranteed | The website can detect or challenge automation. |
| Card entry and payment submission | Recognized actions blocked | Current agent instructions and Python action policy prohibit these operations. |
| Sandbox payment success/failure testing | Feasible extension, not implemented end to end | Needs test-only payment capability, provider configuration, frame support, and outcome verification. |
| Private-network applications | Not generally supported | Public mode rejects non-global addresses; local-development exception covers loopback, not arbitrary private networks. |
| Service-worker/offline/PWA behavior | Not faithful under current configuration | Service workers are explicitly blocked. |
| Downloads, uploads, native applications | Outside current agent tool coverage | Downloads disabled; sensitive/file filling blocked; browser tools are not a native-app automation layer. |

## 1. Origin restrictions affect much more than navigation

[controller.py](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py:227) applies URL and DNS validation to intercepted browser requests. [policy.py](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/policy.py:121) requires approved HTTP(S) origins, with explicit subdomain behavior. WebSocket policy maps WS/WSS to corresponding approved origins.

An approved merchant page can depend on separate origins for scripts, CSS, images, APIs, sign-in, and payment widgets. Allowing the merchant hostname alone does not permit those dependencies. The local policy probe allowed `https://shop.example/pricing` but rejected an external identity origin and `https://js.stripe.com/v3/`. These were string validation calls, not network requests.

Stripe's integration guide documents separate script, frame, and connection origins for its products, illustrating why one merchant origin is insufficient. Its CSP lists are useful dependency evidence, but should not be copied blindly into MarketTwin's distinct authorization policy. [Stripe integration security guide](https://docs.stripe.com/security/guide).

Recommended design: define separate permissions for top-level navigation, embedded resources/frames, identity providers, and test-payment services. Build a preflight report of denied dependencies and require explicit configured scope; do not automatically trust arbitrary origins just because page content requests them. Adding a resource permission should not silently grant permission for the persona to browse that provider's entire website.

Retain DNS/IP checks and add the network-level egress controls already called for in the architecture document. The app's lookup and Chromium's connection do not constitute proof against every DNS or redirect edge case. This research is not a penetration test or a certification of universal isolation.

## 2. Authentication is a capability still being completed

Each journey creates a fresh Chromium context in [create_session](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py:118), without an authenticated storage-state input. It does not inherit the user's normal browser session.

[human_control.py](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/human_control.py:14) has useful primitives: pause traces/capture, change session state, disable agent tools, and resume the same context. However, [HumanActionPage.tsx](C:/Users/sreen/OneDrive/Desktop/MarketTwin/apps/web/src/pages/runs/HumanActionPage.tsx:1) renders a future-stage placeholder. These hooks are not a complete authenticated testing experience.

Implement an authenticated viewer, ownership/lease checks, explicit pause/resume state, and verification that login succeeded in the same journey context. Include authorized identity-provider origins in the journey policy. For regression suites, an application-owned test-account fixture can also provision authenticated state. Playwright supports reusable authentication state and notes that such files contain sensitive session material; keep that state isolated and out of model prompts and source control. [Playwright authentication](https://playwright.dev/python/docs/auth).

For usability studies about login, retain the login interaction as part of the study. For studies of post-login features, preauthenticated test fixtures may be appropriate. Reusing privileged evaluator state in the persona would change what is being tested.

## 3. Browser-engine capability exceeds the current tool interface

Playwright supports explicit frame locators; page-level actions target the main frame. MarketTwin's [semantic_locator](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/actions.py:10) accepts a `Page` and role/label/text, with no frame identifier. Its observation script reads the current document rather than building a frame inventory. [Playwright frames](https://playwright.dev/python/docs/frames).

This matters for payments: Stripe documents the Payment Element as an iframe that communicates payment information to Stripe. Extending a permitted frame's observation and interaction through Playwright is the relevant approach; ordinary parent-page JavaScript is not a universal way to inspect embedded content. [Stripe Payment Element integration](https://docs.stripe.com/connect/separate-charges-and-transfers?platform=web&ui=elements).

Add approved frame IDs, parent relationships, origin, scene version, and explicit frame-scoped actions. Revalidate frames after navigation/re-rendering. Translate child-frame coordinates when relating observations to viewport screenshots. Test nested and cross-origin frames separately; our local `srcdoc` fixture does not establish real Stripe compatibility.

Open shadow roots need a consistent observation path as well. Playwright locators can cross open roots, but the custom collector uses `document.querySelectorAll`. The local probe found the shadow button with a role locator and in ARIA, while `visible_elements` omitted it. Closed roots are not supported by standard Playwright locators. [Playwright Shadow DOM documentation](https://playwright.dev/python/docs/locators#locate-in-shadow-dom).

Canvas-only content needs visual evidence because drawn pixels need not exist as DOM text. The local fixture drew a total that was absent from the model payload. A screenshot can contain the content, but the current persona does not receive screenshot pixels just because an artifact path exists. Visual extraction/verification must be an explicit operation with provenance and uncertainty. Avoid using visual reasoning for every ordinary text page; targeted escalation is cheaper and easier to validate.

## 4. What “see payment info” can mean

**Public purchase information:** prices, taxes shown in the UI, shipping fees, subscription periods, discounts, renewal conditions, accepted payment methods, and checkout error text can be part of a permitted observation. Preserve amount, currency, period, and qualifiers together. The preceding token-efficiency audit already reproduced a missing billing qualifier, so this is not yet universally reliable.

**Authenticated billing information:** invoices, plan status, billing address, and masked card labels can be inspected when an authorized account exposes them and capture policy permits it. MarketTwin has no inherent access to accounts or provider databases. A masked display is not a mechanism for recovering the hidden card number or security code. Restrict model-visible data to what the study actually needs.

**Entering payment details or submitting a payment:** the current [action policy](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/action_policy.py:48) blocks recognized purchase/payment phrases and sensitive card-field metadata. The local probe confirmed recognized payment button and card-field rejection. Reading a displayed price is distinct from performing that transaction.

These checks are phrase/metadata heuristics, not a complete transaction-intent classifier. The generic label `Continue` passed the isolated check; no transaction was performed. A production design needs explicit permitted operations, test-mode evidence, and persisted policy decisions rather than relying on button wording to establish whether an operation is financially consequential.

**Testing payment behavior:** add a separate sandbox capability on applications the user is authorized to test. Configure test credentials outside the model, use provider test values, and verify environment identity before granting the operation. Stripe documents sandbox simulations for success, declines, and authentication without moving funds, and directs users not to test with real card details. [Stripe testing](https://docs.stripe.com/testing).

Do not make the LLM invent or manage payment credentials. A deterministic test adapter can choose a named scenario such as successful payment or declined payment, execute the authorized sandbox operation, and return only the relevant result. UI-driven sandbox tests must still exercise the actual checkout UI; API-only tests validate a different layer and cannot establish usability.

Check the merchant order state and verified provider test events as well as the browser result. A success-looking page alone is insufficient evidence of complete payment handling. Stripe recommends event-based handling rather than relying only on a redirect to a success page. [Stripe post-payment events](https://docs.stripe.com/payments/existing-customers?platform=web&ui=stripe-hosted#handle-post-payment-events).

## 5. Capture controls need work before sensitive billing studies

The intended human-control pause stops screenshot and trace capture. But [the console handler](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py:306) does not check that flag. The local probe passed a synthetic error event to a paused session and confirmed it remained in the event buffer. Page-error and failed-request handlers also require review; [write_event_logs](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/evidence.py:81) persists the accumulated buffers.

This proves a pause-control gap, not an observed leak of real credentials. It matters because error strings and request URLs may contain sensitive values. Resuming screenshots while sensitive fields remain visible is another path to review. No systematic redaction layer was found in the audited capture path.

Introduce a unified capture policy covering model observations, ARIA, screenshots, traces, logs, URLs, and artifact metadata. Suppress or sanitize at collection boundaries; redacting only the final report is too late. Reconcile the post-handoff page before capture resumes. Use synthetic canary values to verify that every output channel remains clean. Keep authoritative nonsensitive facts such as total, currency, order status, and relevant error type available so privacy controls do not destroy test quality.

Using a payment provider does not automatically establish MarketTwin's data-handling compliance. Prefer provider-hosted sensitive collection and limited test-result metadata over ingesting raw payment credentials. The provider's guidance describes why integrations that avoid handling raw card data reduce scope. [Stripe integration security guide](https://docs.stripe.com/security/guide).

## 6. Some websites require explicit testing arrangements

Cloudflare states that automated browsers can be detected by Turnstile and recommends dummy keys for controlled integration tests. For an owned staging site, use those supported testing facilities or an agreed testing configuration. Do not represent challenge handling as universal access or spend repeated agent calls on an unresolved challenge. [Cloudflare Turnstile testing](https://developers.cloudflare.com/turnstile/troubleshooting/testing/).

MarketTwin also blocks service workers in the current context. This helps request interception, but can change applications that depend on worker behavior. Playwright documents the relationship between service workers and interception. A separate, explicitly tested execution profile would be needed for faithful PWA/offline coverage. [Playwright network documentation](https://playwright.dev/docs/network#missing-network-events-and-service-workers).

Browser/OS/device differences, regional availability, permissions, and site-specific authentication can create additional coverage limits. The current journey configuration is one Chromium viewport; it is not proof of Safari, mobile-wallet, or native-system-dialog behavior. Expose these limits instead of promising universal compatibility.

## Recommended architecture and quality gates

Retain the existing Python controller as the browser authority. Extend it in this order:

1. **Preflight capability assessment:** approved origins and dependencies, auth requirement, frame/shadow/canvas presence, challenge state, and supported browser profile.
2. **Complete observations and scope:** recoverable inventory, frame references, consistent shadow-root semantics, qualifiers, and explicit omission metadata.
3. **Capture policy and authenticated handoff:** close the log-pause gap, add redaction tests, and complete same-context human control.
4. **Sandbox payment adapter:** explicit environment checks, permitted named scenarios, bounded retries, and independent order/provider verification.
5. **Quality-gated context optimization:** perform reversible encoding and selection only after the required evidence can be observed and safely retained.

Report access status independently of product findings. Proposed states include supported, partially observed, authentication required, challenged, dependency blocked, and unsupported interaction. These are proposed additions, not existing implemented enums. A provider frame blocked by MarketTwin policy must not automatically become a claim that the merchant's checkout is broken. Conversely, an unobserved payment outcome cannot be reported as passed.

Acceptance fixtures should cover third-party resource denial, authorized SSO, expired sessions, nested frames, shadow controls, canvas totals, taxes/currency/annual billing, declines, authentication-required payments, delayed events, and capture canaries. Use provider sandbox integrations for payment outcome validation. Local DOM fixtures alone cannot establish real-provider compatibility.

## Verification performed

[access_probe.py](access_probe.py) exercised the real collector in local Chromium and called the current policy functions. [access-probe-results.json](access-probe-results.json) records the results and limitations. Thirty-five existing URL-policy, DNS-policy, and action-policy tests passed; Ruff passed for the new probe.

```powershell
.venv/Scripts/python.exe docs/research/website-access/access_probe.py
.venv/Scripts/python.exe -m pytest services/execution-orchestrator/tests/test_browser_policy.py services/execution-orchestrator/tests/test_browser_network.py services/execution-orchestrator/tests/test_browser_action_policy.py -q -p no:cacheprovider
```

The appropriate product claim is broad testing of authorized web applications with declared capability coverage, plus deliberately implemented authentication and sandbox-payment support. “All websites and all payment information” is not supported by the current architecture or this evidence.
