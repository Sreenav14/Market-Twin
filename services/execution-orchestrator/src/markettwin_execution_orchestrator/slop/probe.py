"""The page probe (U-P6-04): one evaluate() that returns everything
the deterministic slop rules measure. Raw page data only — judging
lives in measure.py, which is pure and testable without a browser.

Doc 24 section 2.3 (W4-P5-13) extends the probe ADDITIVELY: every
field the v1 rules read is byte-identical to before; the new fields
(style facts, stylesheet and motion censuses, section and SVG
censuses) feed the catalogue v2 detectors, which must read them
defensively — an older capture without a field simply cannot fire
the codes that need it.
"""

def non_html_type(probe: dict) -> str | None:
    mime = str(probe.get("content_type") or "").partition(";")[0].strip().lower()
    return mime if mime and mime not in {"text/html", "application/xhtml+xml"} else None


PROBE_SCRIPT = """
() => {
  if (!['text/html', 'application/xhtml+xml'].includes(document.contentType)) {
    return {url: location.href, content_type: document.contentType};
  }
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
  const buttonLabelClipping = (el) => {
    // Measure non-scrollable clipping bounds separately from the viewport.
    let left = -Infinity, right = Infinity, top = -Infinity, bottom = Infinity;
    for (let node = el; node && node !== document.body; node = node.parentElement) {
      const style = getComputedStyle(node);
      // Simple flow boxes have comparable client dimensions and viewport bounds.
      if (style.transform !== 'none' || ['absolute', 'fixed'].includes(style.position) ||
          ['auto', 'scroll'].includes(style.overflowX) ||
          ['auto', 'scroll'].includes(style.overflowY)) return null;
      const clipsX = style.overflowX === 'hidden' || style.overflowX === 'clip';
      const clipsY = style.overflowY === 'hidden' || style.overflowY === 'clip';
      if (!clipsX && !clipsY) continue;
      const box = node.getBoundingClientRect();
      if (clipsX) {
        left = Math.max(left, box.left + node.clientLeft);
        right = Math.min(right, box.left + node.clientLeft + node.clientWidth);
      }
      if (clipsY) {
        top = Math.max(top, box.top + node.clientTop);
        bottom = Math.min(bottom, box.top + node.clientTop + node.clientHeight);
      }
    }
    if (left === -Infinity && top === -Infinity) return null;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let visibleText = false, horizontal = 0, vertical = 0;
    while (walker.nextNode()) {
      const text = walker.currentNode;
      if (!text.textContent.trim() || !text.parentElement || !visible(text.parentElement)) continue;
      range.selectNodeContents(text);
      for (const box of range.getClientRects()) {
        if (box.width <= 0 || box.height <= 0 ||
            box.bottom <= 0 || box.top >= innerHeight ||
            box.right <= 0 || box.left >= innerWidth) continue;
        const visibleWidth = Math.max(0, Math.min(box.right, right) - Math.max(box.left, left));
        const visibleHeight = Math.max(0, Math.min(box.bottom, bottom) - Math.max(box.top, top));
        visibleText ||= visibleWidth > 0 && visibleHeight > 0;
        horizontal = Math.max(horizontal, box.width - visibleWidth);
        vertical = Math.max(vertical, box.height - visibleHeight);
      }
    }
    return visibleText && (horizontal > 0 || vertical > 0) ? {
      label_clipped_horizontal_px: Math.round(horizontal),
      label_clipped_vertical_px: Math.round(vertical),
    } : null;
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
  const parentKeyOf = (el) => {
    const parts = [];
    let node = el.parentElement;
    while (node && parts.length < 4) {
      const siblings = node.parentElement ? Array.from(node.parentElement.children) : [];
      parts.unshift(node.tagName.toLowerCase() + ':' + siblings.indexOf(node));
      node = node.parentElement;
    }
    return parts.join('>');
  };
  const interactiveSelector = 'a, button, input, select, textarea, [role="button"], [role="link"]';
  const textSelector = 'h1, h2, h3, h4, h5, h6, p, li, td, th, label, span, div, time';
  const seen = new Set();
  const elements = [];
  const collect = (el, kind) => {
    if (seen.has(el)) return;
    seen.add(el);
    if (!visible(el)) return;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const role = roleOf(el);
    const clipping = role === 'button' ? buttonLabelClipping(el) : null;
    const text = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 400);
    elements.push({
      key: elements.length,
      kind,
      tag: el.tagName.toLowerCase(),
      role,
      name: nameOf(el),
      text: kind === 'text' ? text : '',
      x: Math.round(rect.x), y: Math.round(rect.y),
      width: Math.round(rect.width), height: Math.round(rect.height),
      ...clipping,
      font_size: parseFloat(style.fontSize) || 0,
      font_weight: parseInt(style.fontWeight) || 400,
      font_family: (style.fontFamily || '').slice(0, 120),
      color: style.color || '',
      background: backgroundOf(el),
      border_radius: style.borderRadius,
      padding: style.padding,
      disabled: Boolean(el.disabled),
      selected: el.getAttribute('aria-selected'),
      expanded: el.getAttribute('aria-expanded'),
      invalid: el.getAttribute('aria-invalid'),
      region: el.closest('header,footer,nav,main')?.tagName.toLowerCase() || 'body',
      background_image: style.backgroundImage || 'none',
      background_clip: style.backgroundClip || '',
      own_background: style.backgroundColor || '',
      letter_spacing: style.letterSpacing || '',
      borders: {
        top: {width: style.borderTopWidth, color: style.borderTopColor},
        right: {width: style.borderRightWidth, color: style.borderRightColor},
        bottom: {width: style.borderBottomWidth, color: style.borderBottomColor},
        left: {width: style.borderLeftWidth, color: style.borderLeftColor},
      },
      box_shadow: style.boxShadow || 'none',
      backdrop_filter: style.backdropFilter || 'none',
      filter: style.filter || 'none',
      text_align: style.textAlign || '',
      transform: style.transform || 'none',
      parent_key: parentKeyOf(el),
      child_tags: Array.from(el.children).map((child) => child.tagName.toLowerCase()).slice(0, 12),
    });
  };
  document.querySelectorAll(interactiveSelector).forEach((el) => collect(el, 'interactive'));
  document.querySelectorAll(textSelector).forEach((el) => {
    if (el.children.length === 0) collect(el, 'text');
  });
  const imageStatuses = new Map(performance.getEntriesByType('resource')
    .filter(entry => entry.initiatorType === 'img')
    .map(entry => [entry.name, entry.responseStatus || null]));
  const images = [];
  document.querySelectorAll('img').forEach((img) => {
    if (!visible(img)) return;
    const rect = img.getBoundingClientRect();
    images.push({
      key: images.length,
      src: (img.currentSrc || img.src || '').slice(0, 300),
      alt: img.getAttribute('alt'),
      natural_width: img.naturalWidth, natural_height: img.naturalHeight,
      complete: img.complete,
      response_status: imageStatuses.get(img.currentSrc || img.src) ?? null,
      width: Math.round(rect.width), height: Math.round(rect.height),
      x: Math.round(rect.x), y: Math.round(rect.y),
      object_fit: window.getComputedStyle(img).objectFit || '',
    });
  });
  const stylesheetCensus = () => {
    const sheets = [];
    for (const sheet of Array.from(document.styleSheets)) {
      let rules = null;
      try { rules = sheet.cssRules; } catch (e) { rules = null; }
      if (!rules) {
        sheets.push({readable: false, hover_interactive: false, focus_visible: false});
        continue;
      }
      let hover = false;
      let focus = false;
      for (const rule of Array.from(rules)) {
        const selector = rule.selectorText || '';
        if (!selector) continue;
        if (selector.includes(':focus-visible') || selector.includes(':focus')) focus = true;
        if (selector.includes(':hover')
            && /(^|[\\s,>+~.])(a|button|input|select|textarea|btn|button|link)/.test(selector)) {
          hover = true;
        }
      }
      sheets.push({readable: true, hover_interactive: hover, focus_visible: focus});
    }
    return sheets.slice(0, 40);
  };
  const motionCensus = () => {
    let transitionAll = false;
    let overshoot = false;
    let infinite = false;
    for (const sheet of Array.from(document.styleSheets)) {
      let rules = null;
      try { rules = sheet.cssRules; } catch (e) { rules = null; }
      if (!rules) continue;
      for (const rule of Array.from(rules)) {
        const text = rule.cssText || '';
        if (/transition(-property)?\\s*:\\s*all\\b/.test(text)) transitionAll = true;
        if (/animation[^;]*\\binfinite\\b/.test(text)) infinite = true;
        for (const match of text.matchAll(/cubic-bezier\\(([^)]*)\\)/g)) {
          const numbers = match[1].split(',').map((part) => parseFloat(part));
          if (numbers.length === 4 && (numbers[1] < 0 || numbers[1] > 1
              || numbers[3] < 0 || numbers[3] > 1)) {
            overshoot = true;
          }
        }
      }
    }
    return {transition_all: transitionAll, overshoot_timing: overshoot, infinite_animation: infinite};
  };
  const sectionCensus = () => {
    const root = document.querySelector('main') || document.body;
    if (!root) return [];
    return Array.from(root.children).slice(0, 24).map((el) => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return {
        tag: el.tagName.toLowerCase(),
        y: Math.round(rect.y + window.scrollY),
        height: Math.round(rect.height),
        padding_top: parseFloat(style.paddingTop) || 0,
        padding_bottom: parseFloat(style.paddingBottom) || 0,
      };
    }).filter((section) => section.height >= 40);
  };
  const svgCensus = () => {
    const figures = [];
    document.querySelectorAll('svg').forEach((svg) => {
      const rect = svg.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return;
      let curves = 0;
      svg.querySelectorAll('path').forEach((path) => {
        curves += ((path.getAttribute('d') || '').match(/[CcSsQq]/g) || []).length;
      });
      const fills = new Set();
      svg.querySelectorAll('[fill]').forEach((node) => fills.add(node.getAttribute('fill')));
      figures.push({
        width: Math.round(rect.width), height: Math.round(rect.height),
        curves, fills: fills.size,
        has_text: Boolean(svg.querySelector('text')),
      });
    });
    return figures.slice(0, 24);
  };
  const bodyText = (document.body ? document.body.innerText : '') || '';
  return {
    url: location.href,
    content_type: document.contentType,
    title: document.title || '',
    lang: document.documentElement.getAttribute('lang'),
    scroll_width: document.documentElement.scrollWidth,
    client_width: document.documentElement.clientWidth,
    words: bodyText.trim() ? bodyText.trim().split(/\\s+/).length : 0,
    elements,
    images,
    client_height: document.documentElement.clientHeight,
    device_pixel_ratio: window.devicePixelRatio || 1,
    document_background: backgroundOf(document.body || document.documentElement),
    stylesheets: stylesheetCensus(),
    motion: motionCensus(),
    sections: sectionCensus(),
    svg_figures: svgCensus(),
  };
}
"""
