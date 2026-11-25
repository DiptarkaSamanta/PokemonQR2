const state = {
  payloadMode: 'file',
  directUrl: 'https://pokeapi.co',
  useHostedShortLink: false,
  directRedirect: false,
  inlineText: 'Pikachu says hi from Python!',
  queuedFiles: [],
  bundleLinks: [{ id: crypto.randomUUID(), label: '', url: '' }],
  activeShare: null,
  shareBaseUrl: localStorage.getItem('pokeqr2_share_base_url') || window.location.origin,
  networkInfo: null,
  shares: [],
  autoApplyPalette: true,
  pokemon: {
    id: 25,
    name: 'pikachu',
    displayName: 'Pikachu',
    types: ['electric'],
    shiny: false,
    artworkStyle: 'official',
    customImageDataUrl: null
  },
  style: {
    mode: 'pixelart',
    moduleShape: 'rounded',
    eyeShape: 'pokeball',
    ecLevel: 'H',
    fgColor: '#1e1b4b',
    fgSecondaryColor: '#b45309',
    useGradient: true,
    bgColor: '#fefce8',
    eyeColor: '#d97706',
    badgeSizeRatio: 0.22,
    badgeShape: 'pokeball',
    halftoneIntensity: 0.65,
    backdropOpacity: 0.30,
    pixelSpriteScale: 0.38,
    pixelSafeDots: true,
    neonTheme: 'synthwave',
    neonGlowStrength: 0.75,
    neonInverted: true,
    quietZoneModules: 3,
    includeCardFrame: false,
    cardHeadline: 'Scan to Open PokéDrop',
    cardSubtitle: 'Shared via PokéQR2 (Python)'
  },
  palettes: {}
};

let renderTimer = null;

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function getEffectivePayload() {
  const base = state.shareBaseUrl.replace(/\/+$/, '');
  if (state.payloadMode === 'inline') {
    return state.inlineText.trim() || 'PokéQR2 Python';
  }
  if (state.payloadMode === 'link' && !state.useHostedShortLink) {
    return state.directUrl.trim() || 'https://pokeapi.co';
  }
  if (state.activeShare) {
    return `${base}/s/${state.activeShare.id}`;
  }
  return `${base}/s/demo-pokedrop`;
}

function scheduleQrRender() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(renderQrPreview, 120);
}

async function renderQrPreview() {
  const payload = getEffectivePayload();
  document.getElementById('encoded-payload-code').textContent = payload;
  const openLink = document.getElementById('open-payload-link');
  if (/^https?:\/\//i.test(payload)) {
    openLink.href = payload;
    openLink.classList.remove('hidden');
  } else {
    openLink.classList.add('hidden');
  }

  document.getElementById('preview-title').textContent = `${state.pokemon.displayName} QR`;

  try {
    const res = await fetch('/api/qr/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payload,
        style: state.style,
        pokemon: state.pokemon,
        outputSize: 760,
        format: 'preview'
      })
    });
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('qr-preview-img').src = data.imageDataUrl;
    const v = data.verification;
    const pill = document.getElementById('scan-pill');
    const warn = document.getElementById('scan-warning-banner');
    document.getElementById('grid-size-label').textContent = `${v.moduleCount}×${v.moduleCount} grid`;

    if (v.verified) {
      pill.className = 'scan-pill ok';
      pill.textContent = `OpenCV Scannable${v.inverted ? ' (Neon)' : ''} · ${v.contrastRatio}:1`;
    } else {
      pill.className = 'scan-pill warn';
      pill.textContent = `Check Contrast · ${v.contrastRatio}:1`;
    }
    if (v.warning) {
      warn.textContent = v.warning;
      warn.classList.remove('hidden');
    } else {
      warn.classList.add('hidden');
    }
  } catch (err) {
    console.error(err);
  }
}

async function downloadExport(format, outputSize) {
  const payload = getEffectivePayload();
  const res = await fetch('/api/qr/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      payload,
      style: state.style,
      pokemon: state.pokemon,
      outputSize,
      format
    })
  });
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = format === 'svg' ? `pokeqr2-${state.pokemon.name}.svg` : `pokeqr2-${state.pokemon.name}-${outputSize}px.png`;
  a.click();
  URL.revokeObjectURL(url);
}

function applyPokemonPalette(types) {
  const primary = (types && types[0] ? types[0].toLowerCase() : 'normal');
  const pal = state.palettes[primary] || state.palettes.normal;
  if (!pal) return;
  state.style.fgColor = pal.fg;
  state.style.fgSecondaryColor = pal.fgSecondary;
  state.style.eyeColor = pal.eye;
  state.style.bgColor = pal.bg;
  document.getElementById('fg-color').value = pal.fg;
  document.getElementById('fg2-color').value = pal.fgSecondary;
  document.getElementById('eye-color').value = pal.eye;
  document.getElementById('bg-color').value = pal.bg;
  document.getElementById('selected-pokemon-banner').style.background = pal.badgeBg;
}

function updateSelectedPokemonBanner() {
  const p = state.pokemon;
  const imgSrc = p.artworkStyle === 'custom' && p.customImageDataUrl
    ? p.customImageDataUrl
    : `/api/pokemon/${p.id}/sprite?style=${encodeURIComponent(p.artworkStyle)}&shiny=${p.shiny ? '1' : '0'}&type=${encodeURIComponent(p.types[0] || 'normal')}`;
  document.getElementById('selected-pokemon-img').src = imgSrc;
  document.getElementById('selected-pokemon-name').textContent = p.displayName;
  document.getElementById('selected-pokemon-id').textContent = `#${String(p.id).padStart(3, '0')}`;
  document.getElementById('selected-pokemon-types').innerHTML = (p.types || []).map((t) => `<span class="type-pill">${esc(t)}</span>`).join('');
  const pal = state.palettes[(p.types && p.types[0]) || 'normal'];
  if (pal) document.getElementById('selected-pokemon-banner').style.background = pal.badgeBg;
}

async function selectPokemon(summary, applyPalette) {
  let types = summary.types || [];
  if (!types.length) {
    try {
      const r = await fetch(`/api/pokemon/${summary.id}`);
      if (r.ok) {
        const detail = await r.json();
        types = detail.types || ['normal'];
      }
    } catch {
      types = ['normal'];
    }
  }
  state.pokemon = {
    ...state.pokemon,
    id: summary.id,
    name: summary.name,
    displayName: summary.displayName,
    types: types.length ? types : ['normal'],
    artworkStyle: state.pokemon.artworkStyle === 'custom' ? 'official' : state.pokemon.artworkStyle,
    customImageDataUrl: null
  };
  updateSelectedPokemonBanner();
  if (applyPalette) applyPokemonPalette(state.pokemon.types);
  scheduleQrRender();
}

async function loadPokemonGrid(query = '') {
  const url = query.trim() ? `/api/pokemon?q=${encodeURIComponent(query.trim())}&limit=24` : '/api/pokemon/featured';
  const res = await fetch(url);
  if (!res.ok) return;
  const data = await res.json();
  const grid = document.getElementById('pokemon-grid');
  const items = (data.results || []).slice(0, 24);
  if (!items.length) {
    grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:16px;color:#475569;">No Pokémon matched "${esc(query)}".</div>`;
    return;
  }
  grid.innerHTML = items.map((item) => {
    const selected = item.id === state.pokemon.id && state.pokemon.artworkStyle !== 'custom';
    const art = state.pokemon.artworkStyle === 'custom' ? 'official' : state.pokemon.artworkStyle;
    const src = `/api/pokemon/${item.id}/sprite?style=${encodeURIComponent(art)}&shiny=${state.pokemon.shiny ? '1' : '0'}`;
    return `
      <button type="button" class="pokemon-tile ${selected ? 'selected' : ''}" data-poke-id="${item.id}">
        <img src="${src}" alt="${esc(item.displayName)}" loading="lazy" />
        <span class="tile-name">${esc(item.displayName)}</span>
        <span class="tile-id">#${String(item.id).padStart(3, '0')}</span>
      </button>`;
  }).join('');

  grid.querySelectorAll('[data-poke-id]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const pid = Number(btn.getAttribute('data-poke-id'));
      const found = items.find((i) => i.id === pid);
      if (found) {
        selectPokemon(found, state.autoApplyPalette);
        grid.querySelectorAll('.pokemon-tile').forEach((el) => el.classList.remove('selected'));
        btn.classList.add('selected');
      }
    });
  });
}

function syncModePanels() {
  const m = state.style.mode;
  ['pixelart', 'neonscene', 'badge', 'halftone', 'backdrop'].forEach((name) => {
    document.getElementById(`subpanel-${name}`).classList.toggle('hidden', m !== name);
  });
  document.getElementById('shape-controls-wrap').classList.toggle('hidden', m === 'pixelart' || m === 'neonscene');
  document.getElementById('color-controls-wrap').classList.toggle('hidden', m === 'neonscene');
  document.getElementById('gradient-toggle-wrap').classList.toggle('hidden', m === 'pixelart');
  document.getElementById('fg2-swatch').classList.toggle('hidden', m === 'pixelart' || !state.style.useGradient);
}

function syncPayloadTabs() {
  const m = state.payloadMode;
  document.getElementById('link-section').classList.toggle('hidden', m !== 'link');
  document.getElementById('bundle-links-section').classList.toggle('hidden', m !== 'bundle');
  document.getElementById('file-drop-section').classList.toggle('hidden', m !== 'file' && m !== 'bundle');
  document.getElementById('inline-section').classList.toggle('hidden', m !== 'inline');
  const needsHosted = m === 'file' || m === 'bundle' || (m === 'link' && state.useHostedShortLink);
  document.getElementById('hosted-options-details').classList.toggle('hidden', !needsHosted);
  document.getElementById('submit-share-bar').classList.toggle('hidden', !needsHosted);
  document.getElementById('direct-redirect-wrap').classList.toggle('hidden', !(m === 'link' && state.useHostedShortLink));
  updateActiveShareBanner();
  scheduleQrRender();
}

function updateActiveShareBanner() {
  const banner = document.getElementById('active-share-banner');
  const show = state.activeShare && (state.payloadMode !== 'link' || state.useHostedShortLink) && state.payloadMode !== 'inline';
  if (!show) {
    banner.classList.add('hidden');
    return;
  }
  document.getElementById('active-share-title').textContent = `Active PokéDrop: ${state.activeShare.title}`;
  document.getElementById('active-share-url-hint').textContent = `${state.shareBaseUrl}/s/${state.activeShare.id}`;
  banner.classList.remove('hidden');
}

function renderQueuedFiles() {
  const ul = document.getElementById('queued-files-list');
  ul.innerHTML = state.queuedFiles.map((f, idx) => `
    <li>
      <div><strong>${esc(f.name)}</strong> <span style="color:#475569;font-size:0.78rem;">(${formatBytes(f.size)})</span></div>
      <button type="button" class="icon-btn" data-remove-file="${idx}">Remove</button>
    </li>`).join('');
  ul.querySelectorAll('[data-remove-file]').forEach((b) => {
    b.addEventListener('click', () => {
      state.queuedFiles.splice(Number(b.getAttribute('data-remove-file')), 1);
      renderQueuedFiles();
    });
  });
}

function renderBundleLinks() {
  const list = document.getElementById('bundle-links-list');
  list.innerHTML = state.bundleLinks.map((row, idx) => `
    <div class="bundle-link-row">
      <input type="text" placeholder="Label" value="${esc(row.label)}" data-bl-label="${idx}" />
      <input type="url" placeholder="https://..." value="${esc(row.url)}" data-bl-url="${idx}" />
      ${state.bundleLinks.length > 1 ? `<button type="button" class="icon-btn" data-bl-del="${idx}">×</button>` : ''}
    </div>`).join('');
  list.querySelectorAll('[data-bl-label]').forEach((inp) => inp.addEventListener('input', (e) => {
    state.bundleLinks[Number(inp.getAttribute('data-bl-label'))].label = e.target.value;
  }));
  list.querySelectorAll('[data-bl-url]').forEach((inp) => inp.addEventListener('input', (e) => {
    state.bundleLinks[Number(inp.getAttribute('data-bl-url'))].url = e.target.value;
  }));
  list.querySelectorAll('[data-bl-del]').forEach((btn) => btn.addEventListener('click', () => {
    state.bundleLinks.splice(Number(btn.getAttribute('data-bl-del')), 1);
    renderBundleLinks();
  }));
}

async function refreshShares() {
  const res = await fetch('/api/shares');
  if (!res.ok) return;
  const data = await res.json();
  state.shares = data.shares || [];
  document.getElementById('shares-count').textContent = String(state.shares.length);
  renderSharesManager();
}

function renderSharesManager() {
  const container = document.getElementById('shares-list');
  if (!state.shares.length) {
    container.innerHTML = '<div class="empty-box"><h3>Your PC Box is empty</h3><p>Upload a file or create a hosted PokéDrop link in the QR Studio.</p></div>';
    return;
  }
  const base = state.shareBaseUrl.replace(/\/+$/, '');
  container.innerHTML = state.shares.map((s) => {
    const url = `${base}/s/${s.id}`;
    const pokeSrc = s.pokemon
      ? `/api/pokemon/${s.pokemon.id}/sprite?style=${encodeURIComponent(s.pokemon.artworkStyle || 'official')}&shiny=${s.pokemon.shiny ? '1' : '0'}`
      : '/api/pokemon/25/sprite?style=official';
    return `
      <article class="share-row-card">
        <img src="${pokeSrc}" alt="${esc(s.pokemon?.displayName || 'Pokémon')}" class="share-row-sprite" />
        <div class="share-row-body">
          <div class="share-row-title">
            <h3>${esc(s.title)}</h3>
            <span class="kind-badge">${esc(s.kind)}</span>
            ${s.hasPin ? '<span class="pin-badge">PIN</span>' : ''}
          </div>
          <div><code>${esc(url)}</code></div>
          <div class="share-row-stats">
            <span>${s.filesCount} file(s)</span>
            <span>${s.linksCount} link(s)</span>
            <span>${s.views} views · ${s.downloads} downloads</span>
          </div>
        </div>
        <div class="share-row-actions">
          <button type="button" class="btn btn-primary btn-sm" data-load-share="${esc(s.id)}">Make QR</button>
          <a href="/s/${esc(s.id)}" target="_blank" rel="noopener noreferrer" class="btn btn-ghost btn-sm">Open</a>
          <button type="button" class="btn btn-danger btn-sm" data-del-share="${esc(s.id)}">Delete</button>
        </div>
      </article>`;
  }).join('');

  container.querySelectorAll('[data-load-share]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const s = state.shares.find((item) => item.id === btn.getAttribute('data-load-share'));
      if (!s) return;
      state.activeShare = s;
      state.payloadMode = s.kind === 'link' ? 'link' : s.kind === 'bundle' ? 'bundle' : 'file';
      if (s.kind === 'link') {
        state.useHostedShortLink = true;
        document.getElementById('hosted-short-link-check').checked = true;
      }
      if (s.pokemon) selectPokemon(s.pokemon, state.autoApplyPalette);
      document.querySelectorAll('[data-payload-mode]').forEach((t) => t.classList.toggle('active', t.getAttribute('data-payload-mode') === state.payloadMode));
      switchMainTab('studio');
      syncPayloadTabs();
    });
  });

  container.querySelectorAll('[data-del-share]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-del-share');
      const r = await fetch(`/api/shares/${encodeURIComponent(id)}`, { method: 'DELETE' });
      if (r.ok) {
        if (state.activeShare?.id === id) state.activeShare = null;
        await refreshShares();
        updateActiveShareBanner();
      }
    });
  });
}

function switchMainTab(tab) {
  document.querySelectorAll('[data-main-tab]').forEach((b) => b.classList.toggle('active', b.getAttribute('data-main-tab') === tab));
  document.getElementById('studio-view').classList.toggle('hidden', tab !== 'studio');
  document.getElementById('shares-view').classList.toggle('hidden', tab !== 'shares');
}

function updateNetworkDisplay() {
  const btn = document.getElementById('network-btn');
  document.getElementById('network-btn-label').textContent = state.shareBaseUrl.replace(/^https?:\/\//, '');
  const isLocal = state.shareBaseUrl.includes('localhost') || state.shareBaseUrl.includes('127.0.0.1');
  btn.classList.toggle('warn-local', isLocal);
  if (state.networkInfo) {
    const opts = document.getElementById('network-options');
    const items = [...(state.networkInfo.lanAddresses || []), { url: state.networkInfo.requestOrigin, label: 'Current browser origin', isPrimary: false }];
    opts.innerHTML = items.map((o) => `
      <button type="button" class="network-option ${state.shareBaseUrl === o.url ? 'selected' : ''}" data-base-opt="${esc(o.url)}">
        <div class="opt-url">${esc(o.url)}</div>
        <div class="opt-label">${esc(o.label)}${o.isPrimary ? ' · Recommended' : ''}</div>
      </button>`).join('');
    opts.querySelectorAll('[data-base-opt]').forEach((b) => {
      b.addEventListener('click', () => {
        state.shareBaseUrl = b.getAttribute('data-base-opt').replace(/\/+$/, '');
        localStorage.setItem('pokeqr2_share_base_url', state.shareBaseUrl);
        document.getElementById('network-popover').classList.add('hidden');
        updateNetworkDisplay();
        updateActiveShareBanner();
        scheduleQrRender();
      });
    });
  }
}

async function submitHostedShare() {
  const errEl = document.getElementById('payload-error');
  errEl.classList.add('hidden');
  const btn = document.getElementById('submit-share-btn');
  btn.disabled = true;

  try {
    const linksPayload = [];
    if (state.payloadMode === 'link') {
      if (!state.directUrl.trim()) throw new Error('Enter a link URL first.');
      linksPayload.push({ label: document.getElementById('share-title').value.trim(), url: state.directUrl.trim() });
    } else if (state.payloadMode === 'bundle') {
      state.bundleLinks.forEach((item) => {
        if (item.url.trim()) linksPayload.push({ label: item.label.trim(), url: item.url.trim() });
      });
    }

    if (state.payloadMode === 'file' && !state.queuedFiles.length) throw new Error('Drop or select at least one file.');
    if (state.payloadMode === 'bundle' && !state.queuedFiles.length && !linksPayload.length) throw new Error('Add at least one link or file.');

    const form = new FormData();
    const title = document.getElementById('share-title').value.trim();
    const note = document.getElementById('share-note').value.trim();
    const slug = document.getElementById('share-slug').value.trim();
    const pin = document.getElementById('share-pin').value.trim();
    const exp = document.getElementById('share-expiry').value;
    const maxDl = document.getElementById('share-max-dl').value.trim();

    if (title) form.append('title', title);
    if (note) form.append('note', note);
    if (slug) form.append('customSlug', slug);
    if (pin) form.append('pin', pin);
    form.append('expiresIn', exp);
    if (maxDl) form.append('maxDownloads', maxDl);
    form.append('directRedirect', String(state.payloadMode === 'link' && state.directRedirect));
    form.append('pokemon', JSON.stringify({
      id: state.pokemon.id,
      name: state.pokemon.name,
      displayName: state.pokemon.displayName,
      types: state.pokemon.types,
      shiny: state.pokemon.shiny,
      artworkStyle: state.pokemon.artworkStyle
    }));
    if (linksPayload.length) form.append('links', JSON.stringify(linksPayload));
    state.queuedFiles.forEach((f) => form.append('files', f));

    const track = document.getElementById('upload-progress-track');
    const fill = document.getElementById('upload-progress-fill');
    if (state.queuedFiles.length) track.classList.remove('hidden');

    const result = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/shares');
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable) fill.style.width = `${Math.round((evt.loaded / evt.total) * 100)}%`;
      };
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else reject(new Error(data.detail || 'Upload failed'));
        } catch {
          reject(new Error(`Server error (${xhr.status})`));
        }
      };
      xhr.onerror = () => reject(new Error('Network error while uploading share'));
      xhr.send(form);
    });

    state.activeShare = result.share;
    state.queuedFiles = [];
    document.getElementById('share-slug').value = '';
    document.getElementById('share-pin').value = '';
    renderQueuedFiles();
    updateActiveShareBanner();
    await refreshShares();
    scheduleQrRender();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    document.getElementById('upload-progress-track').classList.add('hidden');
    document.getElementById('upload-progress-fill').style.width = '0%';
  }
}

async function init() {
  // Fetch palettes & network & shares
  const [palRes, netRes] = await Promise.all([fetch('/api/qr/palettes'), fetch('/api/network')]);
  if (palRes.ok) {
    state.palettes = (await palRes.json()).palettes || {};
    const row = document.getElementById('palette-dots-row');
    row.innerHTML = Object.values(state.palettes).slice(0, 12).map((pal) => `
      <button type="button" class="palette-dot" title="${esc(pal.label)} Type" data-pal-name="${esc(pal.name)}"
        style="background:linear-gradient(135deg, ${pal.fg} 50%, ${pal.accent} 50%)"></button>`).join('');
    row.querySelectorAll('[data-pal-name]').forEach((b) => b.addEventListener('click', () => {
      applyPokemonPalette([b.getAttribute('data-pal-name')]);
      scheduleQrRender();
    }));
  }
  if (netRes.ok) {
    state.networkInfo = await netRes.json();
    if (!localStorage.getItem('pokeqr2_share_base_url') && state.networkInfo.recommendedShareBase) {
      state.shareBaseUrl = state.networkInfo.recommendedShareBase;
    }
    updateNetworkDisplay();
  }

  // Bind UI events
  document.querySelectorAll('[data-main-tab]').forEach((b) => b.addEventListener('click', () => switchMainTab(b.getAttribute('data-main-tab'))));
  document.getElementById('network-btn').addEventListener('click', () => {
    document.getElementById('custom-base-url').value = state.shareBaseUrl;
    document.getElementById('network-popover').classList.toggle('hidden');
  });
  document.getElementById('apply-base-url').addEventListener('click', () => {
    const val = document.getElementById('custom-base-url').value.trim().replace(/\/+$/, '');
    if (val) {
      state.shareBaseUrl = val;
      localStorage.setItem('pokeqr2_share_base_url', val);
      document.getElementById('network-popover').classList.add('hidden');
      updateNetworkDisplay();
      updateActiveShareBanner();
      scheduleQrRender();
    }
  });

  document.querySelectorAll('[data-payload-mode]').forEach((tab) => tab.addEventListener('click', () => {
    state.payloadMode = tab.getAttribute('data-payload-mode');
    document.querySelectorAll('[data-payload-mode]').forEach((t) => t.classList.toggle('active', t === tab));
    syncPayloadTabs();
  }));
  document.getElementById('direct-url-input').addEventListener('input', (e) => {
    state.directUrl = e.target.value;
    if (!state.useHostedShortLink) state.activeShare = null;
    scheduleQrRender();
  });
  document.getElementById('hosted-short-link-check').addEventListener('change', (e) => {
    state.useHostedShortLink = e.target.checked;
    if (!e.target.checked) state.activeShare = null;
    syncPayloadTabs();
  });
  document.getElementById('direct-redirect-check').addEventListener('change', (e) => { state.directRedirect = e.target.checked; });
  document.getElementById('inline-text-input').addEventListener('input', (e) => {
    state.inlineText = e.target.value;
    const len = new TextEncoder().encode(state.inlineText).length;
    const ctr = document.getElementById('inline-byte-counter');
    ctr.textContent = `${len} / 1273 bytes`;
    ctr.classList.toggle('over', len > 1273);
    scheduleQrRender();
  });
  document.getElementById('inline-file-btn').addEventListener('click', () => document.getElementById('inline-file-input').click());
  document.getElementById('inline-file-input').addEventListener('change', (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 900) {
      alert(`File is ${formatBytes(f.size)} — use "Share Files" tab for files larger than 900 bytes.`);
      return;
    }
    const r = new FileReader();
    r.onload = () => {
      document.getElementById('inline-text-input').value = r.result;
      state.inlineText = r.result;
      scheduleQrRender();
    };
    r.readAsDataURL(f);
  });

  const dz = document.getElementById('file-dropzone');
  const fi = document.getElementById('file-input');
  dz.addEventListener('click', () => fi.click());
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('dragging'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('dragging'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault(); dz.classList.remove('dragging');
    state.queuedFiles.push(...Array.from(e.dataTransfer.files));
    renderQueuedFiles();
  });
  fi.addEventListener('change', (e) => {
    state.queuedFiles.push(...Array.from(e.target.files));
    renderQueuedFiles();
  });
  document.getElementById('add-bundle-link').addEventListener('click', () => {
    state.bundleLinks.push({ id: crypto.randomUUID(), label: '', url: '' });
    renderBundleLinks();
  });
  document.getElementById('submit-share-btn').addEventListener('click', submitHostedShare);
  document.getElementById('clear-active-share').addEventListener('click', () => {
    state.activeShare = null;
    updateActiveShareBanner();
    scheduleQrRender();
  });

  // Pokemon picker
  let searchTimer = null;
  document.getElementById('pokemon-search-input').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadPokemonGrid(e.target.value), 180);
  });
  document.getElementById('random-pokemon-btn').addEventListener('click', async () => {
    const id = Math.floor(Math.random() * 1025) + 1;
    const r = await fetch(`/api/pokemon/${id}`);
    if (r.ok) selectPokemon(await r.json(), state.autoApplyPalette);
  });
  document.getElementById('shiny-toggle').addEventListener('click', (e) => {
    state.pokemon.shiny = !state.pokemon.shiny;
    e.currentTarget.classList.toggle('active-shiny', state.pokemon.shiny);
    updateSelectedPokemonBanner();
    loadPokemonGrid(document.getElementById('pokemon-search-input').value);
    scheduleQrRender();
  });
  document.getElementById('apply-type-colors').addEventListener('click', () => {
    applyPokemonPalette(state.pokemon.types);
    scheduleQrRender();
  });
  document.getElementById('auto-palette-check').addEventListener('change', (e) => { state.autoApplyPalette = e.target.checked; });
  document.querySelectorAll('[data-art-style]').forEach((b) => b.addEventListener('click', () => {
    state.pokemon.artworkStyle = b.getAttribute('data-art-style');
    state.pokemon.customImageDataUrl = null;
    document.querySelectorAll('[data-art-style]').forEach((el) => el.classList.toggle('active', el === b));
    updateSelectedPokemonBanner();
    loadPokemonGrid(document.getElementById('pokemon-search-input').value);
    scheduleQrRender();
  }));
  document.getElementById('custom-sprite-btn').addEventListener('click', () => document.getElementById('custom-sprite-input').click());
  document.getElementById('custom-sprite-input').addEventListener('change', (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => {
      state.pokemon.artworkStyle = 'custom';
      state.pokemon.customImageDataUrl = r.result;
      state.pokemon.displayName = f.name.replace(/\.[^.]+$/, '').slice(0, 32) || state.pokemon.displayName;
      updateSelectedPokemonBanner();
      scheduleQrRender();
    };
    r.readAsDataURL(f);
  });

  // Style controls
  document.querySelectorAll('[data-qr-mode]').forEach((b) => b.addEventListener('click', () => {
    state.style.mode = b.getAttribute('data-qr-mode');
    document.querySelectorAll('[data-qr-mode]').forEach((el) => el.classList.toggle('active', el === b));
    syncModePanels();
    scheduleQrRender();
  }));
  document.getElementById('pixel-scale-range').addEventListener('input', (e) => {
    state.style.pixelSpriteScale = Number(e.target.value);
    document.getElementById('pixel-scale-val').textContent = String(Math.round(state.style.pixelSpriteScale * 100));
    scheduleQrRender();
  });
  document.getElementById('pixel-safe-dots').addEventListener('change', (e) => { state.style.pixelSafeDots = e.target.checked; scheduleQrRender(); });
  document.getElementById('classic-bw-btn').addEventListener('click', () => {
    state.style.fgColor = '#0f172a'; state.style.fgSecondaryColor = '#0f172a'; state.style.eyeColor = '#0f172a'; state.style.bgColor = '#ffffff';
    document.getElementById('fg-color').value = '#0f172a'; document.getElementById('eye-color').value = '#0f172a'; document.getElementById('bg-color').value = '#ffffff';
    scheduleQrRender();
  });
  document.querySelectorAll('[data-neon-theme]').forEach((b) => b.addEventListener('click', () => {
    state.style.neonTheme = b.getAttribute('data-neon-theme');
    document.querySelectorAll('[data-neon-theme]').forEach((el) => el.classList.toggle('active', el === b));
    scheduleQrRender();
  }));
  document.getElementById('neon-glow-range').addEventListener('input', (e) => {
    state.style.neonGlowStrength = Number(e.target.value);
    document.getElementById('neon-glow-val').textContent = String(Math.round(state.style.neonGlowStrength * 100));
    scheduleQrRender();
  });
  document.getElementById('neon-inverted-check').addEventListener('change', (e) => { state.style.neonInverted = e.target.checked; scheduleQrRender(); });
  document.getElementById('badge-size-range').addEventListener('input', (e) => {
    state.style.badgeSizeRatio = Number(e.target.value);
    document.getElementById('badge-size-val').textContent = String(Math.round(state.style.badgeSizeRatio * 100));
    scheduleQrRender();
  });
  document.querySelectorAll('[data-badge-shape]').forEach((b) => b.addEventListener('click', () => {
    state.style.badgeShape = b.getAttribute('data-badge-shape');
    document.querySelectorAll('[data-badge-shape]').forEach((el) => el.classList.toggle('active', el === b));
    scheduleQrRender();
  }));
  document.getElementById('halftone-range').addEventListener('input', (e) => {
    state.style.halftoneIntensity = Number(e.target.value);
    document.getElementById('halftone-val').textContent = String(Math.round(state.style.halftoneIntensity * 100));
    scheduleQrRender();
  });
  document.getElementById('backdrop-range').addEventListener('input', (e) => {
    state.style.backdropOpacity = Number(e.target.value);
    document.getElementById('backdrop-val').textContent = String(Math.round(state.style.backdropOpacity * 100));
    scheduleQrRender();
  });
  document.querySelectorAll('[data-module-shape]').forEach((b) => b.addEventListener('click', () => {
    state.style.moduleShape = b.getAttribute('data-module-shape');
    document.querySelectorAll('[data-module-shape]').forEach((el) => el.classList.toggle('active', el === b));
    scheduleQrRender();
  }));
  document.querySelectorAll('[data-eye-shape]').forEach((b) => b.addEventListener('click', () => {
    state.style.eyeShape = b.getAttribute('data-eye-shape');
    document.querySelectorAll('[data-eye-shape]').forEach((el) => el.classList.toggle('active', el === b));
    scheduleQrRender();
  }));
  document.getElementById('use-gradient-check').addEventListener('change', (e) => {
    state.style.useGradient = e.target.checked; syncModePanels(); scheduleQrRender();
  });
  ['fg-color', 'fg2-color', 'eye-color', 'bg-color'].forEach((id) => {
    document.getElementById(id).addEventListener('input', (e) => {
      if (id === 'fg-color') state.style.fgColor = e.target.value;
      if (id === 'fg2-color') state.style.fgSecondaryColor = e.target.value;
      if (id === 'eye-color') state.style.eyeColor = e.target.value;
      if (id === 'bg-color') state.style.bgColor = e.target.value;
      scheduleQrRender();
    });
  });
  document.getElementById('card-frame-check').addEventListener('change', (e) => {
    state.style.includeCardFrame = e.target.checked;
    document.getElementById('card-text-inputs').classList.toggle('hidden', !e.target.checked);
    scheduleQrRender();
  });
  document.getElementById('card-headline').addEventListener('input', (e) => { state.style.cardHeadline = e.target.value; scheduleQrRender(); });
  document.getElementById('card-subtitle').addEventListener('input', (e) => { state.style.cardSubtitle = e.target.value; scheduleQrRender(); });

  // Export & copy
  document.getElementById('dl-png-1024').addEventListener('click', () => downloadExport('png', 1024));
  document.getElementById('dl-png-2048').addEventListener('click', () => downloadExport('png', 2048));
  document.getElementById('dl-svg').addEventListener('click', () => downloadExport('svg', 900));
  document.getElementById('copy-payload-btn').addEventListener('click', async () => {
    await navigator.clipboard.writeText(getEffectivePayload());
  });
  document.getElementById('copy-img-btn').addEventListener('click', async () => {
    const src = document.getElementById('qr-preview-img').src;
    if (!src || typeof ClipboardItem === 'undefined') return;
    const blob = await (await fetch(src)).blob();
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
  });
  document.getElementById('refresh-shares-btn').addEventListener('click', refreshShares);

  renderBundleLinks();
  syncPayloadTabs();
  syncModePanels();
  updateSelectedPokemonBanner();
  await Promise.all([loadPokemonGrid(''), refreshShares()]);
  await renderQrPreview();
}

init();
