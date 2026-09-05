document.addEventListener("DOMContentLoaded",()=>{
  const body=document.body, saved=localStorage.getItem('akmv-theme');
  if(saved&&['midnight','cinema','ocean','light'].includes(saved))body.dataset.theme=saved;
  document.querySelectorAll('[data-theme-toggle]').forEach(button=>button.addEventListener('click',()=>{const next=body.dataset.theme==='light'?(body.dataset.baseTheme||'midnight'):'light';body.dataset.theme=next;localStorage.setItem('akmv-theme',next);button.textContent=next==='light'?'☀':'☾'}));
  document.querySelectorAll('[data-back]').forEach(button=>button.addEventListener('click',()=>history.length>1?history.back():location.assign('/')));
  const themeSelect=document.getElementById('siteTheme');if(themeSelect)themeSelect.value=body.dataset.baseTheme||'midnight';
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
