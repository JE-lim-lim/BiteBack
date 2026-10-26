(() => {
 const $=s=>document.querySelector(s), root=document.body;
 const saved=key=>{try{return localStorage.getItem('biteback-'+key)}catch(e){return null}}, store=(key,val)=>{try{localStorage.setItem('biteback-'+key,val)}catch(e){}};
 const get=(id,def)=>{const el=$('#'+id);return el?el.value:(saved(id==='themeChoice'?'theme':id==='fontChoice'?'font':'density')||def)};
 function apply(){const theme=get('themeChoice','light'),font=get('fontChoice','normal'),density=get('densityChoice','comfortable');root.dataset.theme=theme;root.dataset.font=font;root.dataset.density=density;
 document.querySelectorAll('.theme-logo').forEach(img=>{const small=img.classList.contains('sidebar-logo')&&document.body.classList.contains('sidebar-collapsed');img.src=small?'/static/biteback-logo-small.png':(theme==='dark'?'/static/biteback-logo-darkmode.png':'/static/biteback-logo.png');img.onerror=()=>{img.style.display='none';if(img.nextElementSibling)img.nextElementSibling.style.display='inline-flex'}});
 store('theme',theme);store('font',font);store('density',density)}
 ['themeChoice','fontChoice','densityChoice'].forEach(id=>{const el=$('#'+id);if(el){const key=id==='themeChoice'?'theme':id==='fontChoice'?'font':'density';el.value=saved(key)||el.value;el.addEventListener('change',apply)}});
 const fontRange=$('#fontSizeRange'), fontChoice=$('#fontChoice');
 const fontValues=['small','normal','large'];
 if(fontRange){
   const storedFont=saved('font')||'normal';
   fontRange.value=String(Math.max(0,fontValues.indexOf(storedFont)));
   if(fontChoice)fontChoice.value=fontValues[Number(fontRange.value)]||'normal';
   fontRange.addEventListener('input',()=>{if(fontChoice)fontChoice.value=fontValues[Number(fontRange.value)]||'normal';apply()});
 }
 apply();
 const backdrop=$('#settingsBackdrop');const openBtn=$('#settingsOpen')||$('#appSettingsOpen');if(openBtn&&backdrop)openBtn.onclick=()=>backdrop.classList.add('open');const close=$('#settingsClose');if(close&&backdrop)close.onclick=()=>backdrop.classList.remove('open');if(backdrop)backdrop.addEventListener('click',e=>{if(e.target===backdrop)backdrop.classList.remove('open')});
 document.querySelectorAll('.food-orb').forEach(orb=>{let drag=false,sx=0,sy=0,ox=0,oy=0;orb.addEventListener('pointerdown',e=>{drag=true;orb.setPointerCapture(e.pointerId);sx=e.clientX;sy=e.clientY;const r=orb.getBoundingClientRect(),parent=$('#spaceScene').getBoundingClientRect();ox=r.left-parent.left;oy=r.top-parent.top;orb.classList.add('dragging')});orb.addEventListener('pointermove',e=>{if(!drag)return;const p=$('#spaceScene').getBoundingClientRect();orb.style.left=Math.max(0,Math.min(p.width-orb.offsetWidth,ox+e.clientX-sx))+'px';orb.style.top=Math.max(0,Math.min(p.height-orb.offsetHeight,oy+e.clientY-sy))+'px';orb.style.right='auto';orb.style.bottom='auto';orb.style.animation='none'});const end=()=>{drag=false;orb.classList.remove('dragging')};orb.addEventListener('pointerup',end);orb.addEventListener('pointercancel',end);orb.addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const r=orb.getBoundingClientRect(),p=$('#spaceScene').getBoundingClientRect();orb.style.left=Math.max(0,Math.min(p.width-orb.offsetWidth,r.left-p.left+(e.key==='ArrowRight'?16:e.key==='ArrowLeft'?-16:0)))+'px';orb.style.top=Math.max(0,Math.min(p.height-orb.offsetHeight,r.top-p.top+(e.key==='ArrowDown'?16:e.key==='ArrowUp'?-16:0)))+'px';orb.style.right='auto';orb.style.bottom='auto';orb.style.animation='none'}})});

})();