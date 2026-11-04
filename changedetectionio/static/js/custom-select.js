/* Accessible themed dropdown enhancement. Native <select> remains source of truth. */
(() => {
  'use strict';
  function enhance(select) {
    if (!select || select.dataset.customReady) return;
    select.dataset.customReady = '1';
    select.tabIndex = -1;
    const root = document.createElement('span');
    root.className = 'cd-select';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cd-select-trigger';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-label', select.getAttribute('aria-label') ||
      (document.querySelector(`label[for="${CSS.escape(select.id)}"]`) || {}).textContent || 'Select option');
    const label = document.createElement('span'); label.className = 'cd-select-value';
    const arrow = document.createElementNS('http://www.w3.org/2000/svg','svg');
    arrow.classList.add('cd-select-arrow'); arrow.setAttribute('aria-hidden','true');
    arrow.setAttribute('viewBox','0 0 24 24');arrow.setAttribute('fill','none');
    arrow.setAttribute('stroke','currentColor');arrow.setAttribute('stroke-width','2');
    arrow.setAttribute('stroke-linecap','round');arrow.setAttribute('stroke-linejoin','round');
    const chevron = document.createElementNS('http://www.w3.org/2000/svg','polyline');
    chevron.setAttribute('points','6 9 12 15 18 9');arrow.append(chevron);
    button.append(label, arrow);
    select.parentNode.insertBefore(root, select.nextSibling);
    root.append(button);
    select.classList.add('cd-select-native');
    const list = document.createElement('div');
    list.className = 'cd-select-popup';
    list.setAttribute('role','listbox');
    list.hidden = true;
    document.body.append(list); // portal avoids ancestors with overflow:hidden
    let open = false, focusIndex = -1;
    const options = () => Array.from(select.options).filter(o => !o.disabled && !o.hidden);
    function update() {
      label.textContent = select.selectedOptions[0]?.textContent || 'Select';
      button.disabled = select.disabled;
      for (const option of list.querySelectorAll('[role=option]')) {
        const chosen = option.dataset.value === select.value;
        option.setAttribute('aria-selected', String(chosen));
      }
    }
    function position() {
      if (!open) return;
      const box = button.getBoundingClientRect();
      const maxWidth = Math.max(160, Math.min(box.width, window.innerWidth - 16));
      const roomBelow = window.innerHeight - box.bottom;
      const popupHeight = Math.min(280, Math.max(40, list.scrollHeight));
      const below = roomBelow >= popupHeight || roomBelow >= box.top;
      list.style.width = `${maxWidth}px`;
      list.style.left = `${Math.max(8, Math.min(box.left, window.innerWidth - maxWidth - 8))}px`;
      list.style.maxHeight = `${Math.max(80, (below ? roomBelow : box.top) - 12)}px`;
      list.style.top = `${below ? box.bottom + 4 : Math.max(8, box.top - Math.min(popupHeight, box.top - 12) - 4)}px`;
    }
    function close(restoreFocus = false) {
      if (!open) return;
      open = false;
      list.hidden = true;
      button.setAttribute('aria-expanded','false');
      if (restoreFocus) button.focus();
    }
    function choose(option) {
      if (!option || option.disabled) return;
      select.value = option.value;
      // Existing application handlers receive the same native change event.
      select.dispatchEvent(new Event('change', {bubbles:true}));
      update(); close(true);
    }
    function render() {
      const items = options();
      list.replaceChildren();
      items.forEach((option,index) => {
        const item = document.createElement('button');
        item.type = 'button'; item.className='cd-select-option';
        item.setAttribute('role','option'); item.dataset.value = option.value;
        item.textContent = option.textContent;
        item.tabIndex = -1;
        item.addEventListener('click', () => choose(option));
        item.addEventListener('mousemove', () => { focusIndex = index; });
        list.append(item);
      });
      focusIndex = Math.max(0, items.findIndex(o => o.value === select.value));
      update();
    }
    function show() {
      if (select.disabled) return;
      if (open) { close(); return; }
      render(); open = true; list.hidden = false;
      button.setAttribute('aria-expanded','true'); position();
      list.children[focusIndex]?.scrollIntoView({block:'nearest'});
    }
    button.addEventListener('click', show);
    button.addEventListener('keydown', event => {
      if (['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape'].includes(event.key)) event.preventDefault();
      if (event.key === 'Escape') { close(true); return; }
      if (!open) { if (['Enter',' ','ArrowDown','ArrowUp'].includes(event.key)) show(); return; }
      const items = options();
      if (!items.length) return;
      if (event.key === 'ArrowDown') focusIndex = Math.min(items.length-1,focusIndex+1);
      if (event.key === 'ArrowUp') focusIndex = Math.max(0,focusIndex-1);
      if (event.key === 'Home') focusIndex = 0;
      if (event.key === 'End') focusIndex = items.length-1;
      if (event.key === 'Enter' || event.key === ' ') { choose(items[focusIndex]); return; }
      list.children[focusIndex]?.scrollIntoView({block:'nearest'});
      list.children[focusIndex]?.classList.add('cd-focused');
      for (let i=0;i<list.children.length;i++) if (i!==focusIndex) list.children[i].classList.remove('cd-focused');
    });
    document.addEventListener('pointerdown', e => { if (open && !root.contains(e.target) && !list.contains(e.target)) close(); });
    window.addEventListener('resize',position);
    window.addEventListener('scroll',position,true);
    select.addEventListener('change',update);
    select.addEventListener('cd-select-sync',update);
    const observer = new MutationObserver(() => { if (open) {render(); position();} else update(); });
    observer.observe(select,{attributes:true,childList:true,subtree:true,attributeFilter:['disabled','label','selected']});
    update();
  }
  const init = () => document.querySelectorAll('select[data-custom-select]').forEach(enhance);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
  window.CDSelect = {enhance, sync(select) {
    if (select) select.dispatchEvent(new Event('cd-select-sync'));
  }};
})();
