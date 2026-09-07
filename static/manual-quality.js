(() => {
  'use strict';

  // Manual quality selector: prefer 4K on first detection, then let the user
  // choose any real source quality. Never pretend an unavailable quality exists.
  let initialized = false;

  function chooseInitialQuality() {
    const list = document.querySelector('#vlQualities');
    if (!list || initialized) return;
    const buttons = [...list.querySelectorAll('.vl-quality')];
    const available = buttons.filter(b => !b.disabled && b.classList.contains('available'));
    if (!available.length) return;

    // First choice is 4K when the source really exposes 2160p.
    const fourK = available.find(b => /^(4K|2160p)$/i.test((b.dataset.vlQuality || b.textContent || '').trim()));
    const preferred = fourK || available.find(b => /1080p/i.test(b.dataset.vlQuality || b.textContent)) || available[0];
    preferred.click();
    initialized = true;
  }

  function addManualHint() {
    const head = document.querySelector('.vl-quality-head');
    if (!head || head.querySelector('.manual-quality-hint')) return;
    const hint = document.createElement('small');
    hint.className = 'manual-quality-hint';
    hint.textContent = 'Manual selection';
    hint.style.cssText = 'display:block;margin-top:5px;color:#9da8c5;font-size:10px';
    head.insertAdjacentElement('afterend', hint);
  }

  function boot() {
    addManualHint();
    chooseInitialQuality();
    const list = document.querySelector('#vlQualities');
    if (!list) return;
    const observer = new MutationObserver(() => {
      // If the source changes, allow one fresh initial choice.
      if (!list.querySelector('.vl-quality.available')) return;
      if (!initialized) chooseInitialQuality();
    });
    observer.observe(list, {childList:true, subtree:true});

    // A newly fetched URL creates a new quality list; reset only when the
    // application explicitly enters its loading state.
    setInterval(() => {
      if (list.textContent.includes('Detecting real source qualities')) initialized = false;
    }, 500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
