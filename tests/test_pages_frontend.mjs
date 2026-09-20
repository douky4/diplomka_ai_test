import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';

export async function run() {
  const calls = [];
  const context = { URLSearchParams, crypto: { randomUUID: () => 'request-id' },
    QUIZ_CONFIG: {backend:'supabase',url:'https://example.supabase.co',key:'sb_publishable_test'},
    fetch: async (url, options) => {
      const method = url.split('/').at(-1), args = JSON.parse(options.body);
      calls.push({method,args});
      assert.equal(options.headers.apikey, 'sb_publishable_test');
      const data = method === 'quiz_create' ? {participant_id:'p'} : method === 'quiz_resume'
        ? {next_index:0,images:[{image_id:'opaque',src:'media/hash.png'}]} : {success:true};
      return {ok:true,status:200,json:async()=>data};
    }};
  context.window=context;
  vm.createContext(context);
  vm.runInContext(await readFile(new URL('../quiz-api.js',import.meta.url),'utf8'),context);
  const api=context.quizApi;
  for(let i=0;i<2;i++) await api.request('/api/participants',{body:JSON.stringify({age:25,gender:'jiné',experience:'denni'})});
  assert.equal(calls[0].args.p_request_id,calls[1].args.p_request_id);
  await api.request('/api/quiz/p');
  const images=await (await api.request('/api/images?participant_id=p')).json();
  assert.equal(images[0].src,'media/hash.png');
  assert.equal(calls.filter(c=>c.method==='quiz_resume').length,1);
  await api.request('/api/answers',{body:JSON.stringify({participant_id:'p',question_index:0,image_id:'opaque',answer:'ai',confidence:5,ai_reason:'why'})});
  assert.equal(calls.at(-1).args.p_confidence,5);
  assert.equal(calls.at(-1).args.p_image_id,'opaque');
  context.fetch=async()=>({ok:false,status:400,json:async()=>({code:'P0002',message:'missing'})});
  assert.equal((await api.request('/api/quiz/missing')).status,404);
  vm.runInContext(await readFile(new URL('../analytics.js',import.meta.url),'utf8'),context);
  const a=context.quizAnalytics;
  const report=a.analyze({participants:[{id:'p',age:25}],images:[{image_id:'i',question:{correct:'ai',subject_id:'pair'}}],answers:[
    {participant_id:'p',image_id:'i',answer:'ai',confidence:5},
    {participant_id:'p',image_id:'i',answer:'photo',confidence:4,ai_reason:'=FORMULA()'}]});
  assert.equal(report.accuracy,50);
  assert.equal(report.avg_confidence,4.5);
  assert.equal(report.weighted_score,55);
  assert.equal(report.images[0].confident_errors,1);
  const csv=a.csv(a.exportRows(report));
  assert.ok(csv.startsWith('\ufeff'));
  assert.ok(csv.includes("'=FORMULA()"));
  assert.ok(csv.includes('subject_id'));
  return 'Pages frontend OK: RPC mapping, retry identity, resume cache, confidence, errors, metrics and safe CSV';
}
