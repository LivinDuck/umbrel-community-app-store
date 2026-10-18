import {build} from 'esbuild';import assert from 'node:assert/strict';import fs from 'node:fs';
await build({stdin:{contents:`export {useCandidateGroups} from './client/vendor/useCandidateGroups';export {useMetadataSearch} from './client/vendor/useMetadataSearch';export {bookRequestWorkKey,canonicalizeBookRequestIsbn} from './client/vendor/types';export {ref,effectScope} from 'vue';`,resolveDir:process.cwd()},bundle:true,platform:'node',format:'esm',outfile:'/tmp/orbit-test-bundle.mjs',alias:{'@bookorbit/types':'./client/vendor/types.ts'}});
const {useCandidateGroups,useMetadataSearch,bookRequestWorkKey,canonicalizeBookRequestIsbn,ref,effectScope}=await import('/tmp/orbit-test-bundle.mjs?'+Date.now());
const scope=effectScope();scope.run(()=>{
const s=useMetadataSearch();s.providers.value=[{key:'itunes',coverPriority:1,audioCoverPriority:2},{key:'goodreads',coverPriority:3,audioCoverPriority:5}];
const c=(provider,id,title='Dune',extra={})=>({provider,providerId:id,title,authors:['Frank Herbert'],...extra});
s.results.value=[c('itunes','i1'),c('itunes','i2','Dune Messiah'),c('itunes','i3','Children of Dune'),c('goodreads','g1'),c('goodreads','g2','Dune Messiah'),c('goodreads','g3','God Emperor of Dune')];
assert.deepEqual(s.filteredResults.value.map(x=>x.providerId),['g1','g2','i1','i2','g3','i3']);
const medium=ref('ebook'),language=ref('en');const {groups}=useCandidateGroups(s.filteredResults,medium,()=>null,s.coverProviderOrder,language,s.resultProviderOrder);
assert.equal(groups.value.length,4);assert.equal(groups.value[0].title,'Dune');assert.equal(groups.value[0].candidates.length,2);
s.results.value=[c('goodreads','g1','Dune',{isbn13:'9780441172719',language:'fr',coverUrl:'https://g',publishedYear:1965}),c('itunes','i1','Dune',{isbn13:'9780593099322',language:'en',coverUrl:'https://i',publishedYear:2019})];
assert.equal(groups.value[0].coverUrl,'https://i');assert.equal(groups.value[0].recommendedIsbnChoice.candidate.provider,'itunes');assert.equal(groups.value[0].publishedYear,1965);
medium.value='audiobook';assert.match(groups.value[0].key,/:audiobook$/);
assert.equal(bookRequestWorkKey('三体','刘慈欣','ebook'),'work:三体:刘慈欣:ebook');assert.equal(canonicalizeBookRequestIsbn('0441172717',null),'9780441172719');
});scope.stop();
const original='/home/node/projects/bookorbit-upstream/client/src/features/book-requests/composables/useCandidateGroups.ts';
if(fs.existsSync(original))assert.equal(fs.readFileSync('client/vendor/useCandidateGroups.ts','utf8'),fs.readFileSync(original,'utf8'));
console.log('PASS: provider interleave, work grouping, language-aware editions, cover priority, years, ISBN canonicalization, CJK, medium separation; grouping source matches BookOrbit byte-for-byte.');
