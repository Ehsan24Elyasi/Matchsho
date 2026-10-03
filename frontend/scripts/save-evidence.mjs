import fs from 'node:fs';
fs.mkdirSync('../docs/pilot/evidence', { recursive: true });
const result=JSON.parse(fs.readFileSync('test-results/results.json','utf8'));
function flatten(suites){return suites.flatMap(s=>[...(s.specs||[]).map(spec=>({title:spec.title,file:spec.file,tests:spec.tests.map(t=>({status:t.status,results:t.results.map(r=>({status:r.status,duration:r.duration,attachments:r.attachments}))}))})),...flatten(s.suites||[])]);}
const specs=flatten(result.suites);
fs.writeFileSync('../docs/pilot/evidence/frontend-contract-results.json',JSON.stringify({generatedAt:new Date().toISOString(),stats:result.stats,specs},null,2));
for(const spec of specs)for(const test of spec.tests)for(const run of test.results)for(const attachment of run.attachments||[])if(attachment.name==='landing-resource-size-report'&&attachment.body){const report=Buffer.from(attachment.body,'base64');const width=JSON.parse(report.toString()).viewport.width;fs.writeFileSync(`../docs/pilot/evidence/frontend-asset-budget-${width}.json`,report);}
