(function (global) {
  function questionFor(answer, catalog) {
    if (answer.metadata_snapshot) {
      try { return JSON.parse(answer.metadata_snapshot); } catch (_) { /* Legacy record. */ }
    }
    const id = answer.image_id || ['real_001', 'fake_001'][answer.question_index];
    return catalog.find(item => item.image_id === id)?.question || { image_id: id };
  }
  function normalize(answer, catalog) {
    const q = questionFor(answer, catalog);
    return { ...answer, image_id: answer.image_id || q.image_id,
      correct_answer: answer.correct_answer || q.correct,
      subject_id: answer.subject_id || q.subject_id,
      metadata: q.metadata || {} };
  }
  function metrics(answers) {
    const valid = answers.filter(a => ['ai', 'photo'].includes(a.correct_answer));
    const correct = valid.filter(a => a.answer === a.correct_answer).length;
    const round = (n, digits) => Number(n.toFixed(digits));
    return { answer_count: valid.length, correct_count: correct,
      accuracy: valid.length ? round(correct / valid.length * 100, 1) : 0,
      avg_confidence: valid.length ? round(valid.reduce((n,a) => n+a.confidence,0)/valid.length,2) : null,
      weighted_score: valid.length ? round(valid.reduce((n,a) => n+50+(a.answer===a.correct_answer?10:-10)*a.confidence,0)/valid.length,1) : null };
  }
  function analyze(data) {
    const answers = data.answers.map(a => normalize(a, data.images));
    const participants = data.participants.map(p => {
      const responses = answers.filter(a => a.participant_id === p.id);
      return { ...p, responses, ...metrics(responses) };
    });
    const images = data.images.map(item => {
      const responses = answers.filter(a => a.image_id === item.image_id);
      return { ...item, responses, ...metrics(responses),
        ai_count: responses.filter(a => a.answer === 'ai').length,
        photo_count: responses.filter(a => a.answer === 'photo').length,
        confident_errors: responses.filter(a => a.answer !== a.correct_answer && a.confidence >= 4).length,
        confidence_counts: [1,2,3,4,5].map(level => ({ level,
          correct: responses.filter(a => a.confidence === level && a.answer === a.correct_answer).length,
          incorrect: responses.filter(a => a.confidence === level && a.answer !== a.correct_answer).length })) };
    });
    const ageGroups = [['Do 20 let',0,20],['21–30 let',21,30],['31–40 let',31,40],['41–50 let',41,50],['51 a více let',51,Infinity]]
      .map(([label,min,max]) => {
        const members = participants.filter(p => p.age >= min && p.age <= max);
        return { label, participants_count: members.length, ...metrics(members.flatMap(p => p.responses)) };
      });
    return { participants, images, answers, ageGroups, ...metrics(answers) };
  }
  function exportRows(data) {
    return data.participants.flatMap(p => p.responses.map(a => ({
      participant_id:p.id,age:p.age,gender:p.gender,experience:p.experience,
      question_index:a.question_index,image_id:a.image_id,subject_id:a.subject_id,
      correct_answer:a.correct_answer,answer:a.answer,is_correct:a.answer===a.correct_answer,
      confidence:a.confidence,weighted_score:50+(a.answer===a.correct_answer?10:-10)*a.confidence,
      ai_reason:a.ai_reason || '',technique:a.technique,difficulty:a.difficulty,source_dataset:a.source_dataset,
      difficulty_intended:a.metadata.difficulty_intended || '',deliberate_cues:a.metadata.deliberate_cues || '',
      participant_created_at:p.created_at,answer_created_at:a.created_at,
    })));
  }
  function csv(rows) {
    if (!rows.length) return '\ufeffparticipant_id,image_id,answer,confidence\r\n';
    const headers = Object.keys(rows[0]);
    const cell = value => {
      let text = value == null ? '' : String(value);
      if (typeof value === 'string' && /^[=+\-@\t\r]/.test(text)) text = "'"+text;
      return '"'+text.replaceAll('"','""')+'"';
    };
    return '\ufeff'+[headers.map(cell).join(','),...rows.map(row => headers.map(h => cell(row[h])).join(','))].join('\r\n');
  }
  global.quizAnalytics = { metrics, analyze, exportRows, csv };
})(globalThis);
