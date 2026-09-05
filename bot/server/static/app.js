const AKMV_THEMES=[
  ['midnight','Midnight'],['cinema','Cinema'],['ocean','Ocean'],
  ['royal','Royal Gold'],['aurora','Aurora Glass'],['amoled','AMOLED Black'],
  ['graphite','Graphite Luxe'],['light','Ivory Daylight']
];
const AKMV_THEME_IDS=AKMV_THEMES.map(([id])=>id);
const AKMV_DARK_THEMES=AKMV_THEME_IDS.filter(id=>id!=='light');
function getThemePreference(key){try{return localStorage.getItem(key)}catch{return null}}
function saveThemePreference(key,value){try{localStorage.setItem(key,value)}catch{}}

document.addEventListener("DOMContentLoaded",()=>{
  const root=document.documentElement;
  const body=document.body;
  const base=AKMV_THEME_IDS.includes(body.dataset.baseTheme)?body.dataset.baseTheme:'midnight';
  const saved=getThemePreference('akmv-theme');
  const initial=AKMV_THEME_IDS.includes(saved)?saved:base;
  let lastDark=getThemePreference('akmv-dark-theme');
  if(!AKMV_DARK_THEMES.includes(lastDark))lastDark=AKMV_DARK_THEMES.includes(initial)?initial:(AKMV_DARK_THEMES.includes(base)?base:'midnight');
  const toggles=[...document.querySelectorAll('[data-theme-toggle]')];
  let picker=document.querySelector('[data-theme-picker]');
  if(toggles.length&&!picker){
    picker=document.createElement('select');picker.className='theme-picker';picker.dataset.themePicker='';picker.setAttribute('aria-label','Choose personal theme');picker.title='Personal theme';
    picker.innerHTML=AKMV_THEMES.map(([id,label])=>`<option value="${id}">${label}</option>`).join('');
    toggles[0].parentElement.insertBefore(picker,toggles[0]);
  }
  const applyTheme=(theme,persist=true)=>{
    const chosen=AKMV_THEME_IDS.includes(theme)?theme:base;
    root.dataset.theme=chosen;
    body.dataset.theme=chosen;
    if(AKMV_DARK_THEMES.includes(chosen)){lastDark=chosen;saveThemePreference('akmv-dark-theme',chosen)}
    if(persist)saveThemePreference('akmv-theme',chosen);
    if(picker)picker.value=chosen;
    toggles.forEach(button=>{const isLight=chosen==='light';button.textContent=isLight?'☾':'☀';button.title=isLight?`Switch to ${AKMV_THEMES.find(([id])=>id===lastDark)?.[1]||'night'} mode`:'Switch to day mode';button.setAttribute('aria-label',button.title)});
  };
  applyTheme(initial,false);
  if(picker)picker.addEventListener('change',()=>applyTheme(picker.value));
  toggles.forEach(button=>button.addEventListener('click',()=>applyTheme(body.dataset.theme==='light'?lastDark:'light')));
  document.querySelectorAll('[data-back]').forEach(button=>button.addEventListener('click',()=>history.length>1?history.back():location.assign('/')));
  const themeSelect=document.getElementById('siteTheme');if(themeSelect)themeSelect.value=base;
  document.querySelectorAll("img[data-src]").forEach(img=>{img.src=img.dataset.src;img.removeAttribute("data-src")});
  const url=new URL(location.href), page=Number(url.searchParams.get("page")||1);
  const setPage=(id,next)=>{const a=document.getElementById(id);if(!a)return;if(next<1){a.classList.add("disabled");return}const target=new URL(url);target.searchParams.set("page",next);a.href=target};
  setPage("prevButton",page-1);setPage("nextButton",page+1);
  document.querySelectorAll("[data-copy]").forEach(button=>button.addEventListener("click",async()=>{await navigator.clipboard.writeText(button.dataset.copy);button.textContent="Copied";setTimeout(()=>button.textContent="Copy link",1200)}));
});
function checkSendButton(){const chosen=[...document.querySelectorAll('#selectCheckbox:checked')];const button=document.getElementById('sendButton');if(button)button.disabled=!chosen.length}
async function sendPopupForm(){
  const chosen=[...document.querySelectorAll('#selectCheckbox:checked')].map(x=>x.dataset.id);
  document.getElementById('selectedIds').value=chosen.join(',');
  const query=document.getElementById('folderSearch'),select=document.getElementById('folderDropdown');
  const load=async()=>{const result=await fetch('/searchDbFol?query='+encodeURIComponent(query.value));const folders=await result.json();select.innerHTML=folders.map(x=>`<option value="${x._id}">${escapeHtml(x.name)}</option>`).join('');document.getElementById('folderId').value=select.value||'root'};
  query.oninput=load;select.onchange=()=>document.getElementById('folderId').value=select.value;await load();
}
function submitSendForm(){const select=document.getElementById('folderDropdown');document.getElementById('folderId').value=select.value||'root'}
function escapeHtml(text){const d=document.createElement('div');d.textContent=String(text);return d.innerHTML}
async function deleteRecord(id,parent){if(!confirm('Delete this item?'))return;const response=await fetch('/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({delete_id:id,parent})});if(response.ok)location.reload();else alert('Delete failed')}
