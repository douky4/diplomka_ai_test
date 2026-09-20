/* Public browser transport. Privileged operations stay inside Supabase RPC functions. */
(function (global) {
  const config = global.QUIZ_CONFIG || { backend: 'flask' };
  let requestId = null;
  let resumed = null;

  async function rpc(name, args = {}) {
    if (!config.url || !config.key) throw new Error('Připojení testu zatím není nastavené.');
    const response = await fetch(config.url + '/rest/v1/rpc/' + name, {
      method: 'POST',
      headers: { apikey: config.key, 'Content-Type': 'application/json' },
      body: JSON.stringify(args),
    });
    const data = await response.json();
    if (!response.ok || data?.error) {
      const error = new Error(data?.error || data?.message || 'Server požadavek nevyřídil.');
      error.status = data?.code === 'P0002' ? 404 : response.status;
      throw error;
    }
    return data;
  }

  function reset() { requestId = null; resumed = null; }

  async function request(path, options = {}) {
    if (config.backend !== 'supabase') return fetch(path, options);
    try {
      const body = options.body ? JSON.parse(options.body) : {};
      let data;
      if (path === '/api/participants') {
        requestId ||= global.crypto.randomUUID();
        data = await rpc('quiz_create', { p_request_id: requestId, p_age: body.age,
          p_gender: body.gender, p_experience: body.experience });
        resumed = null;
      } else if (path.startsWith('/api/quiz/')) {
        const id = decodeURIComponent(path.substring('/api/quiz/'.length));
        resumed = { id, data: await rpc('quiz_resume', { p_participant_id: id }) };
        data = { next_index: resumed.data.next_index };
      } else if (path.startsWith('/api/images?')) {
        const id = new URLSearchParams(path.split('?')[1]).get('participant_id');
        if (resumed?.id !== id) resumed = { id, data: await rpc('quiz_resume', { p_participant_id: id }) };
        data = resumed.data.images;
      } else if (path === '/api/answers') {
        data = await rpc('quiz_answer', { p_participant_id: body.participant_id,
          p_question_index: body.question_index, p_image_id: body.image_id,
          p_answer: body.answer, p_confidence: body.confidence, p_ai_reason: body.ai_reason || '' });
        resumed = null;
      } else throw new Error('Neznámý požadavek');
      return { ok: true, status: 200, json: async () => data };
    } catch (error) {
      return { ok: false, status: error.status || 503, json: async () => ({ error: error.message }) };
    }
  }
  global.quizApi = { request, rpc, reset, backend: config.backend };
})(window);
