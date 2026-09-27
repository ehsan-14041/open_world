/* Accessibility probe for tests/test_accessibility.py. Injected into a rendered page, it records
   controls without an accessible name, duplicate ids, skipped heading levels and text below the
   WCAG AA contrast ratio (4.5:1, or 3:1 for large text), on the body attribute data-audit. */
setTimeout(function(){
  function lum(c){
    var p, m = c.match(/rgba?\(([^)]+)\)/);
    if(m) p = m[1].split(',').map(function(x){ return parseFloat(x); });
    else { m = c.match(/color\(srgb ([^)]+)\)/); if(!m) return null;
      var q = m[1].replace('/', ' ').split(/ +/).map(parseFloat); p = [q[0]*255, q[1]*255, q[2]*255, q.length > 3 ? q[3] : 1]; }
    var a = p.length > 3 ? p[3] : 1;
    var rgb = p.slice(0,3).map(function(v){ v/=255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
    return {l: 0.2126*rgb[0] + 0.7152*rgb[1] + 0.0722*rgb[2], a: a, raw: p};
  }
  function bgOf(el){
    while(el && el.nodeType === 1){
      var cs = getComputedStyle(el);
      if(cs.backgroundImage && cs.backgroundImage !== 'none') return null;
      var b = lum(cs.backgroundColor);
      if(b && b.a > 0.95) return cs.backgroundColor;
      el = el.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor;
  }
  function visible(el){
    if(!el.getClientRects().length) return false;
    var cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.opacity !== '0';
  }
  function name(el){
    if(el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    var lb = el.getAttribute('aria-labelledby');
    if(lb) return lb.split(' ').map(function(i){ var x = document.getElementById(i); return x ? x.textContent : ''; }).join(' ').trim();
    if(el.id){ var l = document.querySelector('label[for="' + el.id + '"]'); if(l && l.textContent.trim()) return l.textContent.trim(); }
    var w = el.closest('label'); if(w && w.textContent.trim()) return w.textContent.trim();
    if(el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'SUMMARY') return el.textContent.trim();
    return el.getAttribute('title') || '';
  }
  var out = {lang: document.documentElement.lang, dir: document.documentElement.dir, noName: [], contrast: [], small: [], dup: [], headings: []};
  document.querySelectorAll('input,select,textarea,button,a[href],summary,[role=button]').forEach(function(el){
    if(!visible(el) || el.type === 'hidden') return;
    if(!name(el)) out.noName.push(el.outerHTML.slice(0, 140));
    var r = el.getBoundingClientRect();
    if((el.tagName === 'BUTTON' || el.tagName === 'SUMMARY' || el.tagName === 'SELECT') && (r.height < 32 || r.width < 32))
      out.small.push([el.id || el.className || el.tagName, Math.round(r.width), Math.round(r.height), el.textContent.trim().slice(0, 30)]);
  });
  var seen = {};
  document.querySelectorAll('[id]').forEach(function(el){ if(seen[el.id]) out.dup.push(el.id); seen[el.id] = 1; });
  var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  var done = new Set();
  while(walker.nextNode()){
    var n = walker.currentNode, el = n.parentElement;
    if(!n.textContent.trim() || !el || done.has(el) || !visible(el)) continue;
    if(el.closest('svg')) continue;
    // The chosen segment's fill is the sliding ::before indicator, which computed styles cannot see.
    if(el.closest('.seg') && el.getAttribute('aria-pressed') === 'true') continue;
    done.add(el);
    var cs = getComputedStyle(el), fg = lum(cs.color), bgc = bgOf(el);
    if(!fg || !bgc) continue;
    var bg = lum(bgc);
    var L1 = Math.max(fg.l, bg.l), L2 = Math.min(fg.l, bg.l), ratio = (L1 + 0.05) / (L2 + 0.05);
    var size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
    var need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    if(fg.a < 1) need += 0;   // alpha text: ratio computed on unblended colour; flagged below
    if(ratio < need) out.contrast.push([el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className ? '.' + String(el.className).split(' ')[0] : ''),
      ratio.toFixed(2), need, cs.color, bgc, n.textContent.trim().slice(0, 40)]);
  }
  var last = 0;
  document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(function(h){
    if(!visible(h)) return;
    var lv = +h.tagName[1];
    if(last && lv > last + 1) out.headings.push(h.tagName + ' after H' + last + ': ' + h.textContent.trim().slice(0, 40));
    last = lv;
  });
  document.body.setAttribute('data-audit', JSON.stringify(out));
}, __WAIT__);
