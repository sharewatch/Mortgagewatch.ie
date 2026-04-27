/* shared.js — inject nav and footer, load rates data */

const NAV_HTML = `
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="nav-logo">
      <div class="nav-logo-mark">
        <svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20">
          <path d="M3 14L7 8L11 11L15 5" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="15" cy="5" r="2" fill="#5DD98A"/>
        </svg>
      </div>
      <span class="nav-logo-text">Mortgage<span>Watch</span>.ie</span>
    </a>
    <ul class="nav-links" id="nav-links">
      <li><a href="/rates.html" data-page="rates">Compare Rates</a></li>
      <li><a href="/lenders/" data-page="lenders">Lenders</a></li>
      <li><a href="/calculator.html" data-page="calculator">Calculator</a></li>
      <li><a href="/first-time-buyers.html" data-page="ftb">First-Time Buyers</a></li>
      <li><a href="/news.html" data-page="news">Rate News</a></li>
      <li><a href="/rates.html" class="nav-cta">See All Rates</a></li>
    </ul>
    <button class="nav-mobile-toggle" onclick="toggleMobileNav()" aria-label="Toggle menu">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>
  </div>
</nav>`;

const FOOTER_HTML = `
<footer>
  <div class="footer-inner">
    <div class="footer-top">
      <div class="footer-brand">
        <a href="/" class="nav-logo" style="display:inline-flex;">
          <div class="nav-logo-mark">
            <svg viewBox="0 0 20 20" fill="none" width="20" height="20"><path d="M3 14L7 8L11 11L15 5" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="15" cy="5" r="2" fill="#5DD98A"/></svg>
          </div>
          <span class="nav-logo-text">Mortgage<span>Watch</span>.ie</span>
        </a>
        <p>Ireland's most up-to-date mortgage rate comparison. We track rates from every major Irish lender so you don't have to.</p>
      </div>
      <div class="footer-col">
        <h4>Compare</h4>
        <ul>
          <li><a href="/rates.html">All Rates</a></li>
          <li><a href="/lenders/aib.html">AIB</a></li>
          <li><a href="/lenders/boi.html">Bank of Ireland</a></li>
          <li><a href="/lenders/ptsb.html">PTSB</a></li>
          <li><a href="/lenders/avant.html">Avant Money</a></li>
        </ul>
      </div>
      <div class="footer-col">
        <h4>Guides</h4>
        <ul>
          <li><a href="/first-time-buyers.html">First-Time Buyers</a></li>
          <li><a href="/switchers.html">Switching Mortgage</a></li>
          <li><a href="/green-mortgages.html">Green Mortgages</a></li>
          <li><a href="/calculator.html">Calculator</a></li>
          <li><a href="/news.html">Rate News</a></li>
        </ul>
      </div>
      <div class="footer-col">
        <h4>About</h4>
        <ul>
          <li><a href="/about.html">About Us</a></li>
          <li><a href="/methodology.html">Our Methodology</a></li>
          <li><a href="/privacy.html">Privacy Policy</a></li>
          <li><a href="/disclaimer.html">Disclaimer</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 MortgageWatch.ie</span>
      <span>Rates updated daily · Data sourced from lender websites</span>
    </div>
    <div class="footer-disclaimer">
      MortgageWatch.ie is an independent comparison website. We are not regulated by the Central Bank of Ireland and do not provide financial advice. Rates shown are indicative and may differ from those offered to you. Always verify current rates directly with your lender or a regulated mortgage broker. We may earn a referral fee when you apply through links on this site.
    </div>
  </div>
</footer>`;

function injectNav(activePage) {
  document.body.insertAdjacentHTML('afterbegin', NAV_HTML);
  if (activePage) {
    const link = document.querySelector(`[data-page="${activePage}"]`);
    if (link) link.classList.add('active');
  }
}

function injectFooter() {
  document.body.insertAdjacentHTML('beforeend', FOOTER_HTML);
}

function toggleMobileNav() {
  const links = document.getElementById('nav-links');
  if (!links) return;
  const open = links.style.display === 'flex';
  Object.assign(links.style, {
    display: open ? '' : 'flex',
    flexDirection: 'column',
    position: open ? '' : 'absolute',
    top: open ? '' : '64px',
    left: open ? '' : '0',
    right: open ? '' : '0',
    background: open ? '' : '#0B1C3D',
    padding: open ? '' : '16px 24px',
    borderTop: open ? '' : '1px solid rgba(255,255,255,0.08)',
    zIndex: open ? '' : '200'
  });
}

async function loadRates() {
  try {
    const res = await fetch('/data/rates.json');
    if (!res.ok) throw new Error('fetch failed');
    return await res.json();
  } catch {
    return null;
  }
}

function termLabel(rate) {
  if (rate.green) return `${rate.term_years}-yr Green`;
  if (rate.type === 'variable') return 'Variable';
  return rate.term_years ? `${rate.term_years}-yr Fixed` : 'Fixed';
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-IE', { day: 'numeric', month: 'short', year: 'numeric' });
}

function calcMonthly(principal, annualRate, termYears) {
  const r = annualRate / 100 / 12;
  const n = termYears * 12;
  if (r === 0) return principal / n;
  return principal * r * Math.pow(1 + r, n) / (Math.pow(1 + r, n) - 1);
}
