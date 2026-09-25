/* orb.js - Jeeves's animated presence: an original SVG magic circle.
 * Rebuilt from the orb made for the original Jeeves on the night of 2026-06-20
 * (see WHAT-I-STOLE.md). No image files, nothing copyrighted: every line is drawn here.
 *
 * Usage:  const orb = JeevesOrb(svgElement, {inner: "text", outer: "text"});
 *         orb.setState('idle' | 'listening' | 'thinking' | 'speaking');
 *         orb.setEnergy(0..1) / orb.clearEnergy();
 *         await orb.attachMic();            // a real microphone drives 'listening'
 *         orb.attachAudioElement(audioEl);  // a real <audio> element drives 'speaking'
 * The two rings of runes spell out the `inner` and `outer` text (set in config.json).
 * One shared animation loop runs every orb on the page, and it pauses while the tab is hidden.
 */
(function () {
  const SVGNS = "http://www.w3.org/2000/svg";
  const el = (t, a = {}) => { const e = document.createElementNS(SVGNS, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
  const FUTHARK = { A:'ᚨ',B:'ᛒ',C:'ᚲ',D:'ᛞ',E:'ᛖ',F:'ᚠ',G:'ᚷ',H:'ᚺ',I:'ᛁ',J:'ᛃ',K:'ᚲ',L:'ᛚ',M:'ᛗ',N:'ᚾ',O:'ᛟ',P:'ᛈ',Q:'ᚲ',R:'ᚱ',S:'ᛊ',T:'ᛏ',U:'ᚢ',V:'ᚹ',W:'ᚹ',X:'ᛪ',Y:'ᛇ',Z:'ᛉ' };
  const rune = s => [...String(s).toUpperCase()].map(c => c === ' ' ? ' ᛫ ' : (FUTHARK[c] || c)).join('');
  const arc = r => `M 200 ${200 - r} A ${r} ${r} 0 1 1 199.99 ${200 - r}`;

  let UID = 0, rafOn = false, cssOn = false;
  const instances = [];

  function injectCSS() {
    if (cssOn) return; cssOn = true;
    const s = document.createElement('style');
    s.textContent = `
      .rp-glyph{fill:#F4C657;font-family:ui-monospace,monospace;font-size:15px;letter-spacing:7px;filter:drop-shadow(0 0 4px rgba(244,198,87,.7))}
      .rp-glyph.rp-outer{font-size:13px;letter-spacing:9px;fill:#ffe6a6}
      .rp-beam{stroke:rgba(244,198,87,.4);stroke-width:1}
      .rp-tick{stroke:rgba(255,230,150,.55);stroke-width:1.4}
      .rp-halo{fill:none;stroke:rgba(255,235,170,.8);stroke-width:1.5;filter:drop-shadow(0 0 6px rgba(255,220,130,.8))}
      .rp-halo2{fill:none;stroke:rgba(244,198,87,.28);stroke-width:1}
      .rp-rays{mix-blend-mode:screen}
      .rp-flare{filter:blur(1.7px);mix-blend-mode:screen}
      .rp-center{filter:drop-shadow(0 0 12px rgba(255,228,150,.95))}
      .rp-glow{filter:blur(11px);mix-blend-mode:screen}
      svg.rp-svg{overflow:visible}
    `;
    document.head.appendChild(s);
  }

  function build(svg, id, innerTxt, outerTxt) {
    svg.classList.add('rp-svg'); svg.setAttribute('viewBox', '0 0 400 400');
    const defs = el('defs'); svg.appendChild(defs);
    // gradients (per-instance ids)
    const core = el('radialGradient', { id: id + '-core', cx: '38%', cy: '34%', r: '62%' });
    [['0%','#FFFDF4'],['22%','#FFE9A8'],['52%','#F4C657'],['80%','#9c6f1e'],['100%','rgba(42,29,6,0)']].forEach(([o,c]) => core.appendChild(el('stop', { offset:o,'stop-color':c })));
    const rayg = el('linearGradient', { id: id + '-ray', x1:'0',y1:'0',x2:'1',y2:'0' });
    rayg.appendChild(el('stop', { offset:'0%','stop-color':'rgba(255,235,170,.95)' }));
    rayg.appendChild(el('stop', { offset:'100%','stop-color':'rgba(244,198,87,0)' }));
    const glowg = el('radialGradient', { id: id + '-glow', cx:'50%',cy:'50%',r:'50%' });
    [['0%','rgba(255,255,255,.95)'],['32%','rgba(255,224,150,.55)'],['70%','rgba(120,200,150,.08)'],['100%','rgba(0,0,0,0)']].forEach(([o,c]) => glowg.appendChild(el('stop', { offset:o,'stop-color':c })));
    const fv = el('linearGradient', { id: id + '-fv', x1:'0',y1:'0',x2:'0',y2:'1' });
    [['0%','transparent'],['50%','#ffffff'],['100%','transparent']].forEach(([o,c]) => fv.appendChild(el('stop',{offset:o,'stop-color':c})));
    const fh = el('linearGradient', { id: id + '-fh', x1:'0',y1:'0',x2:'1',y2:'0' });
    [['0%','transparent'],['50%','#fff7e0'],['100%','transparent']].forEach(([o,c]) => fh.appendChild(el('stop',{offset:o,'stop-color':c})));
    const p1 = el('path', { id: id + '-r1', d: arc(120), fill: 'none' });
    const p2 = el('path', { id: id + '-r2', d: arc(154), fill: 'none' });
    [core, rayg, glowg, fv, fh, p1, p2].forEach(g => defs.appendChild(g));

    // ambient bloom behind everything
    const glow = el('circle', { cx:200, cy:200, r:120, fill:`url(#${id}-glow)`, class:'rp-glow' });
    svg.appendChild(glow);

    // reticle: long beams + ticks
    const beams = el('g');
    for (let i = 0; i < 8; i++) { const a = i*45*Math.PI/180;
      beams.appendChild(el('line', { x1:200+Math.cos(a)*100, y1:200+Math.sin(a)*100, x2:200+Math.cos(a)*196, y2:200+Math.sin(a)*196, class:'rp-beam' })); }
    for (let i = 0; i < 72; i++) { const a = i*5*Math.PI/180, r0 = i%6===0?168:178;
      beams.appendChild(el('line', { x1:200+Math.cos(a)*r0, y1:200+Math.sin(a)*r0, x2:200+Math.cos(a)*190, y2:200+Math.sin(a)*190, class:'rp-tick' })); }
    beams.appendChild(el('circle', { cx:200, cy:200, r:166, class:'rp-halo2' }));
    svg.appendChild(beams);

    // glyph rings
    const mkRing = (pathId, txt, cls) => {
      const g = el('g'); const t = el('text', { class: cls });
      const tp = el('textPath', { href: '#' + pathId });
      tp.setAttributeNS('http://www.w3.org/1999/xlink', 'href', '#' + pathId);
      tp.textContent = txt.repeat(2); t.appendChild(tp); g.appendChild(t); svg.appendChild(g); return g;
    };
    const g1 = mkRing(id + '-r1', innerTxt, 'rp-glyph');
    const g2 = mkRing(id + '-r2', outerTxt, 'rp-glyph rp-outer');

    // halo rings around the blaze
    svg.appendChild(el('circle', { cx:200, cy:200, r:98, class:'rp-halo' }));
    svg.appendChild(el('circle', { cx:200, cy:200, r:106, class:'rp-halo2' }));

    // the blaze: many sharp, varied rays
    const raysWrap = el('g', { class: 'rp-rays' }); const rays = el('g');
    for (let i = 0; i < 96; i++) { const a = i*(360/96)*Math.PI/180;
      const len = (i%8===0)?100 : (i%4===0)?70 : (i%2)?42 : 24;
      rays.appendChild(el('line', { x1:200+Math.cos(a)*6, y1:200+Math.sin(a)*6, x2:200+Math.cos(a)*len, y2:200+Math.sin(a)*len, stroke:`url(#${id}-ray)`, 'stroke-width':1.3, 'stroke-linecap':'round' })); }
    raysWrap.appendChild(rays); svg.appendChild(raysWrap);

    // lens-flare cross-star
    const flare = el('g', { class: 'rp-flare' });
    const mk = (w,h,grad,rot,op) => { const r = el('rect', { x:200-w/2, y:200-h/2, width:w, height:h, fill:`url(#${grad})`, opacity:op }); if (rot) r.setAttribute('transform', `rotate(${rot} 200 200)`); return r; };
    flare.appendChild(mk(3.4, 244, id+'-fv', 0, .95));
    flare.appendChild(mk(244, 3.4, id+'-fh', 0, .9));
    flare.appendChild(mk(2.4, 158, id+'-fv', 45, .45));
    flare.appendChild(mk(2.4, 158, id+'-fv', -45, .45));
    svg.appendChild(flare);

    // white-hot centre — radiant light, not a sphere
    const center = el('g', { class: 'rp-center' });
    center.appendChild(el('circle', { cx:200, cy:200, r:42, fill:`url(#${id}-core)` }));
    center.appendChild(el('circle', { cx:200, cy:200, r:15, fill:'#fffdf6' }));
    svg.appendChild(center);

    return { glow, beams, g1, g2, raysWrap, flare, center };
  }

  function loop(ts) { const t = ts / 1000; if (!document.hidden) { for (const ins of instances) ins._update(t); } requestAnimationFrame(loop); }

  window.JeevesOrb = function (svg, opts = {}) {
    injectCSS();
    const id = 'jo' + (UID++);
    const inner = opts.inner != null ? opts.inner : 'At your service';
    const outer = opts.outer != null ? opts.outer : 'Your second brain is listening';
    const R = build(svg, id, rune(inner) + ' ᛬ ', rune(outer) + ' ᛬ ');

    const ctrl = {
      state: 'idle', manual: null, mic: null, audio: null, actx: null, onEnergy: null,
      _a1: 0, _a2: 0, _ab: 0, _ar: 0,
      setState(s) { this.state = s; return this; },
      setEnergy(e) { this.manual = Math.max(0, Math.min(1, e)); return this; },
      clearEnergy() { this.manual = null; return this; },
      _ctx() { this.actx = this.actx || new (window.AudioContext || window.webkitAudioContext)(); return this.actx; },
      async attachMic() {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          const ctx = this._ctx(); const src = ctx.createMediaStreamSource(stream);
          const an = ctx.createAnalyser(); an.fftSize = 256; src.connect(an); this.mic = an;
          this.state = 'listening'; return true;
        } catch (e) { return false; }
      },
      attachAudioElement(aud) {
        try {
          const ctx = this._ctx(); const src = ctx.createMediaElementSource(aud);
          const an = ctx.createAnalyser(); an.fftSize = 256; src.connect(an); an.connect(ctx.destination); this.audio = an;
        } catch (e) {}
      },
      _live(an) { const d = new Uint8Array(an.frequencyBinCount); an.getByteFrequencyData(d); let s = 0; for (const v of d) s += v; return Math.min(1, (s / d.length) / 110); },
      _energy(t) {
        if (this.state === 'speaking' && this.audio) return Math.max(0.1, this._live(this.audio));
        if (this.state === 'listening' && this.mic) return Math.max(0.08, this._live(this.mic));
        if (this.manual != null) return this.manual;
        switch (this.state) {
          case 'listening': return 0.40 + 0.22 * Math.abs(Math.sin(t*6)) + 0.08 * Math.random();
          case 'thinking':  return 0.30 + 0.20 * Math.sin(t*2.4);
          case 'speaking':  return Math.min(1, 0.50 + 0.40 * Math.abs(Math.sin(t*9)) + 0.18 * Math.random());
          default:          return 0.28 + 0.14 * Math.sin(t*1.7);
        }
      },
      _update(t) {
        const e = this._energy(t);
        this._a1 += 0.34 + e*0.75; this._a2 -= 0.26 + e*0.55; this._ab += 0.11 + e*0.20; this._ar += 0.18 + e*0.40;
        const tw = 0.65 + 0.35 * Math.sin(t*6);
        const sc = (o,k) => `translate(200 200) scale(${(o + e*k).toFixed(3)}) translate(-200 -200)`;
        R.g1.setAttribute('transform', `rotate(${this._a1} 200 200)`);
        R.g2.setAttribute('transform', `rotate(${this._a2} 200 200)`);
        R.beams.setAttribute('transform', `rotate(${this._ab} 200 200)`);
        R.raysWrap.setAttribute('transform', sc(1.12, 0.50) + ` rotate(${this._ar} 200 200)`);
        const thinking = this.state === 'thinking';
        R.flare.setAttribute('transform', sc(0.95, 1.05));
        R.flare.setAttribute('opacity', ((0.62 + e*0.38) * tw).toFixed(3));
        R.center.setAttribute('transform', sc(0.94, 0.40));
        R.center.setAttribute('opacity', thinking ? '0.6' : '1');
        R.glow.setAttribute('transform', sc(0.55, 1.1));
        R.glow.setAttribute('opacity', (0.40 + e*0.5).toFixed(3));
        if (this.onEnergy) this.onEnergy(e);
      }
    };
    instances.push(ctrl);
    if (!rafOn) { rafOn = true; requestAnimationFrame(loop); }
    return ctrl;
  };
})();
