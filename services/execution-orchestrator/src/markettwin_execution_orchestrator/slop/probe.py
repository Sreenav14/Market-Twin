"""The page probe (U-P6-04): one evaluate() that returns everything
the deterministic slop rules measure. Raw page data only — judging
lives in measure.py, which is pure and testable without a browser.
"""

PROBE_SCRIPT = """
() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const roleOf = (el) => {
    const explicit = el.getAttribute && el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'input') return el.type === 'checkbox' ? 'checkbox'
      : el.type === 'radio' ? 'radio' : 'textbox';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'img') return 'img';
    return tag;
  };
  const nameOf = (el) => {
    const label = el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('alt'));
    if (label) return label.trim();
    return (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200);
  };
  const backgroundOf = (el) => {
    let node = el;
    while (node) {
      const bg = window.getComputedStyle(node).backgroundColor;
      if (bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)') return bg;
      node = node.parentElement;
    }
    return 'rgb(255, 255, 255)';
  };
  const interactiveSelector = 'a, button, input, select, textarea, [role="button"], [role="link"]';
  const textSelector = 'h1, h2, h3, h4, h5, h6, p, li, td, th, label, span, div';
  const seen = new Set();
  const elements = [];
  const collect = (el, kind) => {
    if (seen.has(el) || elements.length >= 300) return;
    seen.add(el);
    if (!visible(el)) return;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const text = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 400);
    elements.push({
      key: elements.length,
      kind,
      tag: el.tagName.toLowerCase(),
      role: roleOf(el),
      name: nameOf(el),
      text: kind === 'text' ? text : '',
      x: Math.round(rect.x), y: Math.round(rect.y),
      width: Math.round(rect.width), height: Math.round(rect.height),
      font_size: parseFloat(style.fontSize) || 0,
      font_weight: parseInt(style.fontWeight) || 400,
      font_family: (style.fontFamily || '').slice(0, 120),
      color: style.color || '',
      background: backgroundOf(el),
    });
  };
  document.querySelectorAll(interactiveSelector).forEach((el) => collect(el, 'interactive'));
  document.querySelectorAll(textSelector).forEach((el) => {
    if (el.children.length === 0) collect(el, 'text');
  });
  const images = [];
  document.querySelectorAll('img').forEach((img) => {
    if (!visible(img) || images.length >= 100) return;
    const rect = img.getBoundingClientRect();
    images.push({
      key: images.length,
      src: (img.currentSrc || img.src || '').slice(0, 300),
      alt: img.getAttribute('alt'),
      natural_width: img.naturalWidth, natural_height: img.naturalHeight,
      width: Math.round(rect.width), height: Math.round(rect.height),
    });
  });
  const bodyText = (document.body ? document.body.innerText : '') || '';
  return {
    url: location.href,
    title: document.title || '',
    lang: document.documentElement.getAttribute('lang'),
    scroll_width: document.documentElement.scrollWidth,
    client_width: document.documentElement.clientWidth,
    words: bodyText.trim() ? bodyText.trim().split(/\\s+/).length : 0,
    elements,
    images,
  };
}
"""
