(function () {
  'use strict';

  const yearEl = document.getElementById('footer-year');
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());

  let catalog = { apps: [], upcoming: [] };
  let activeCategory = 'Todas';
  let searchQuery = '';
  const liveReleases = {};

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatMb(bytes) {
    if (!bytes || !Number.isFinite(bytes)) return '';
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatDateEs(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString('es-MX', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  async function fetchLatestRelease(repo, fallbackUrl) {
    try {
      const res = await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
        headers: { Accept: 'application/vnd.github+json' },
      });
      if (!res.ok) return null;
      const data = await res.json();
      const assets = Array.isArray(data.assets) ? data.assets : [];
      const exeAsset =
        assets.find((a) => typeof a.name === 'string' && a.name.toLowerCase().endsWith('.exe')) ||
        assets[0] ||
        null;
      return {
        tag: data.tag_name || '',
        name: data.name || data.tag_name || '',
        body: (data.body || '').trim(),
        publishedAt: data.published_at || '',
        htmlUrl: data.html_url || fallbackUrl,
        downloadUrl: exeAsset ? exeAsset.browser_download_url : data.html_url || fallbackUrl,
        exeName: exeAsset ? exeAsset.name : '',
        sizeMb: exeAsset ? formatMb(exeAsset.size) : '',
      };
    } catch {
      return null;
    }
  }

  function hydrateHero(app, rel) {
    if (!app) return;
    const descEl = document.getElementById('hero-description');
    const badgeEl = document.getElementById('hero-status-badge');
    const verEl = document.getElementById('meta-version');
    const sizeEl = document.getElementById('meta-size');
    const dateEl = document.getElementById('meta-date');
    const cardVerEl = document.getElementById('card-version');
    const dlBtn = document.getElementById('hero-download-btn');
    const dlLabel = document.getElementById('hero-download-label');
    const relBtn = document.getElementById('hero-releases-btn');
    const notesEl = document.getElementById('release-notes-content');
    const featEl = document.getElementById('hero-features');
    const reqEl = document.getElementById('requirements-list');
    const movellaEl = document.getElementById('driver-movella-link');
    const ftdiEl = document.getElementById('driver-ftdi-link');

    if (descEl) descEl.textContent = app.shortDesc || descEl.textContent;
    if (badgeEl) badgeEl.textContent = `${app.status || 'Disponible'} · ${app.platform || 'Windows 10/11'}`;

    const cleanTag = rel && rel.tag ? rel.tag : `v${app.fallbackVersion || '1.0.0'}`;
    if (verEl) verEl.textContent = `Versión ${cleanTag}`;
    if (cardVerEl) cardVerEl.textContent = cleanTag.replace(/^v/i, '');
    if (sizeEl) sizeEl.textContent = rel && rel.sizeMb ? `Instalador ${rel.sizeMb}` : 'Instalador Windows 64-bit';
    if (dateEl) dateEl.textContent = rel && rel.publishedAt ? `Publicado ${formatDateEs(rel.publishedAt)}` : 'GitHub Releases';

    if (dlBtn) dlBtn.href = (rel && rel.downloadUrl) || app.fallbackDownloadUrl;
    if (dlLabel) dlLabel.textContent = `Descargar ${app.name} (${cleanTag})`;
    if (relBtn) relBtn.href = (rel && rel.htmlUrl) || app.fallbackDownloadUrl;
    if (movellaEl && app.driversUrl) movellaEl.href = app.driversUrl;
    if (ftdiEl && app.ftdiDriversUrl) ftdiEl.href = app.ftdiDriversUrl;

    if (notesEl) {
      notesEl.textContent =
        (rel && rel.body) ||
        'Lanzamiento autocontenido para Windows 10/11 con motor XDA oficial, esqueleto de 23 huesos tipo Vicon y exportación Blender.';
    }

    if (featEl && Array.isArray(app.highlights)) {
      featEl.innerHTML = app.highlights.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    }
    if (reqEl && Array.isArray(app.requirements)) {
      reqEl.innerHTML = app.requirements.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
    }
  }

  function renderCategories() {
    const container = document.getElementById('category-pills');
    if (!container) return;
    const cats = ['Todas', ...new Set((catalog.apps || []).map((a) => a.category).filter(Boolean))];
    container.innerHTML = cats
      .map(
        (cat) =>
          `<button type="button" class="pill ${cat === activeCategory ? 'active' : ''}" data-cat="${escapeHtml(cat)}">${escapeHtml(cat)}</button>`,
      )
      .join('');
    container.querySelectorAll('button[data-cat]').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeCategory = btn.getAttribute('data-cat') || 'Todas';
        renderCategories();
        renderCatalog();
      });
    });
  }

  function renderCatalog() {
    const grid = document.getElementById('apps-grid');
    if (!grid) return;

    const filtered = (catalog.apps || []).filter((app) => {
      const catMatch = activeCategory === 'Todas' || app.category === activeCategory;
      const q = searchQuery.trim().toLowerCase();
      const textMatch =
        !q ||
        (app.name || '').toLowerCase().includes(q) ||
        (app.shortDesc || '').toLowerCase().includes(q) ||
        (app.category || '').toLowerCase().includes(q);
      return catMatch && textMatch;
    });

    if (!filtered.length) {
      grid.innerHTML = '<div class="app-card"><p>No se encontraron aplicaciones con ese filtro.</p></div>';
      return;
    }

    grid.innerHTML = filtered
      .map((app) => {
        const rel = liveReleases[app.id];
        const ver = rel && rel.tag ? rel.tag : `v${app.fallbackVersion || '1.0.0'}`;
        const dlUrl = (rel && rel.downloadUrl) || app.fallbackDownloadUrl || '#';
        const sizeLabel = rel && rel.sizeMb ? ` · ${rel.sizeMb}` : '';
        return `
          <article class="app-card">
            <div class="app-card-top">
              <span class="app-cat">${escapeHtml(app.category)}</span>
              <span class="app-status">${escapeHtml(app.status || 'Disponible')}</span>
            </div>
            <h3>${escapeHtml(app.name)}</h3>
            <p>${escapeHtml(app.shortDesc)}</p>
            <div class="app-card-footer">
              <span>${escapeHtml(app.platform)} · <strong>${escapeHtml(ver)}</strong>${escapeHtml(sizeLabel)}</span>
              <a href="${escapeHtml(dlUrl)}" target="_blank" rel="noopener" class="btn btn-primary" style="padding:8px 14px;font-size:0.82rem;">
                Descargar
              </a>
            </div>
          </article>
        `;
      })
      .join('');
  }

  function renderUpcoming() {
    const grid = document.getElementById('upcoming-grid');
    if (!grid) return;
    const list = catalog.upcoming || [];
    grid.innerHTML = list
      .map(
        (item) => `
        <article class="upcoming-card">
          <span class="upcoming-status">${escapeHtml(item.status || 'Próximamente')}</span>
          <h4>${escapeHtml(item.name)}</h4>
          <p>${escapeHtml(item.description)}</p>
        </article>
      `,
      )
      .join('');
  }

  async function init() {
    const searchEl = document.getElementById('search-input');
    if (searchEl) {
      searchEl.addEventListener('input', (e) => {
        searchQuery = e.target.value || '';
        renderCatalog();
      });
    }

    try {
      const res = await fetch('/apps.json', { cache: 'no-cache' });
      catalog = await res.json();
    } catch {
      catalog = { apps: [], upcoming: [] };
    }

    renderCategories();
    renderCatalog();
    renderUpcoming();

    const primary = (catalog.apps || [])[0];
    if (primary) {
      hydrateHero(primary, null);
    }

    await Promise.all(
      (catalog.apps || []).map(async (app) => {
        if (!app.githubRepo) return;
        const rel = await fetchLatestRelease(app.githubRepo, app.fallbackDownloadUrl);
        if (rel) {
          liveReleases[app.id] = rel;
        }
      }),
    );

    if (primary) {
      hydrateHero(primary, liveReleases[primary.id] || null);
    }
    renderCatalog();
  }

  init();
})();
