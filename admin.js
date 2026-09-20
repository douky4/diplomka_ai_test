const login = document.querySelector('#login-form');
const dashboard = document.querySelector('#dashboard');
const adminStatus = document.querySelector('#admin-status');
const tokenKey = 'quiz-admin-session-v1';
let adminToken = sessionStorage.getItem(tokenKey);
let report = null;
let loading = false;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text != null) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function table(headers, rows) {
  const wrapper=node('div',null,'scroll'), t=node('table'), head=node('thead'), tr=node('tr'), body=node('tbody');
  headers.forEach(h=>tr.append(node('th',h))); head.append(tr);t.append(head,body);
  rows.forEach(row=>{const r=node('tr');row.forEach(value=>{
    const cell=node('td');if(value instanceof Node)cell.append(value);else cell.textContent=value ?? '—';r.append(cell);
  });body.append(r);});wrapper.append(t);return wrapper;
}
function responsesTable(responses) {
  return table(['Respondent','Pořadí','Obrázek','Správná odpověď','Odpověď','Jistota','Zdůvodnění'],responses.map(a=>[
    a.participant_id.slice(0,12),a.question_index+1,a.image_id,label(a.correct_answer),label(a.answer),`${a.confidence}/5`,a.ai_reason||'—',
  ]));
}
function label(value) { return value==='ai'?'AI':value==='photo'?'Fotografie':'Neznámá'; }
function renderImages() {
  const target=document.querySelector('#image-results');target.replaceChildren();
  if(!report)return;
  const filter=document.querySelector('#image-filter').value;
  report.images.filter(item=>filter==='all'||item.question.correct===filter).forEach(item=>{
    const card=node('article',null,'card'), summary=node('div',null,'summary');
    const img=node('img');img.src=item.src;img.alt=item.image_id;img.loading='lazy';
    const link=node('a');link.href=item.src;link.target='_blank';link.rel='noopener';link.append(img);
    const text=node('div');text.append(node('h3',`${item.image_id} · ${label(item.question.correct)}`));
    text.append(node('p',`Dvojice: ${item.question.subject_id} · Sada: ${item.question.source_dataset}`));
    text.append(node('p',`Přiděleno: ${item.assigned_count} · Odpovědí: ${item.answer_count}`));
    text.append(node('p',`Volba AI: ${item.ai_count} · Volba fotografie: ${item.photo_count} · Úspěšnost: ${item.accuracy} %`));
    text.append(node('p',`Průměrná jistota: ${item.avg_confidence ?? '—'}/5 · Chyby s jistotou 4–5: ${item.confident_errors}`));
    const metadata=item.question.metadata||{};
    text.append(node('p',`Zamýšlená obtížnost: ${metadata.difficulty_intended||'neuvedena'} · Požadovaná vodítka: ${metadata.deliberate_cues||'žádná'}`,'muted'));
    summary.append(link,text);card.append(summary);
    card.append(table(['Jistota','1/5','2/5','3/5','4/5','5/5'],[
      ['Správně',...item.confidence_counts.map(b=>b.correct)],['Chybně',...item.confidence_counts.map(b=>b.incorrect)],
    ]));
    const details=node('details');details.append(node('summary',`Jednotlivé reakce (${item.answer_count})`),responsesTable(item.responses));
    card.append(details);target.append(card);
  });
}
function render() {
  document.querySelector('#overview').replaceChildren(
    node('h2',`${report.participants.length} respondentů · ${report.answer_count} odpovědí`),
    node('p',`Úspěšnost: ${report.accuracy} % · Průměrná jistota: ${report.avg_confidence ?? '—'}/5 · Vážené skóre: ${report.weighted_score ?? '—'}/100`));
  document.querySelector('#participant-table').replaceChildren(table(
    ['Respondent','Věk','Pohlaví','Zkušenost s AI','Odpovědí','Úspěšnost','Jistota','Vážené skóre','Detail'],
    report.participants.map(p=>{
      const details=node('details');details.append(node('summary','Odpovědi'),responsesTable(p.responses));
      return [p.id.slice(0,12),p.age,p.gender,p.experience,p.answer_count,`${p.accuracy} %`,p.avg_confidence,p.weighted_score,details];
    })));
  document.querySelector('#age-table').replaceChildren(table(
    ['Věková skupina','Respondentů','Odpovědí','Úspěšnost','Průměrná jistota','Vážené skóre'],
    report.ageGroups.map(g=>[g.label,g.participants_count,g.answer_count,`${g.accuracy} %`,g.avg_confidence,g.weighted_score])));
  renderImages();
}
async function loadReport() {
  if(loading)return;loading=true;adminStatus.textContent='Načítám výsledky…';
  document.querySelector('#refresh').disabled=true;
  try {
    const data={participants:[],answers:[],images:[]};let offset=0,more=true;
    while(more){
      const page=await quizApi.rpc('quiz_admin_data',{p_token:adminToken,p_offset:offset});
      data.participants.push(...page.participants);data.answers.push(...page.answers);data.images=page.images;
      more=page.has_more;offset+=200;
    }
    report=quizAnalytics.analyze(data);render();login.hidden=true;dashboard.hidden=false;adminStatus.textContent='Výsledky načteny.';
  }catch(error){
    adminStatus.textContent=error.message;
    if(error.status===401||error.status===403){sessionStorage.removeItem(tokenKey);adminToken=null;login.hidden=false;dashboard.hidden=true;}
  }finally{loading=false;document.querySelector('#refresh').disabled=false;}
}
login.addEventListener('submit',async event=>{
  event.preventDefault();const button=login.querySelector('button');button.disabled=true;
  try{
    const data=await quizApi.rpc('quiz_admin_login',{p_password:document.querySelector('#password').value});
    adminToken=data.token;sessionStorage.setItem(tokenKey,adminToken);document.querySelector('#password').value='';await loadReport();
  }catch(error){adminStatus.textContent=error.message;}finally{button.disabled=false;}
});
document.querySelector('#refresh').addEventListener('click',loadReport);
document.querySelector('#image-filter').addEventListener('change',renderImages);
document.querySelector('#export').addEventListener('click',()=>{
  if(!report)return;
  const url=URL.createObjectURL(new Blob([quizAnalytics.csv(quizAnalytics.exportRows(report))],{type:'text/csv;charset=utf-8'}));
  const link=node('a');link.href=url;link.download='results.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
document.querySelector('#logout').addEventListener('click',async()=>{
  const token=adminToken;adminToken=null;sessionStorage.removeItem(tokenKey);report=null;
  dashboard.hidden=true;login.hidden=false;adminStatus.textContent='Odhlášeno.';
  for(const id of ['#overview','#participant-table','#age-table','#image-results'])document.querySelector(id).replaceChildren();
  try{await quizApi.rpc('quiz_admin_logout',{p_token:token});}catch(_){/* The server token expires automatically. */}
});
if(adminToken)loadReport();
