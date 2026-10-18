import {createApp,computed,ref,h,onMounted,watch} from 'vue'
import {useMetadataSearch} from './vendor/useMetadataSearch'
import {useCandidateGroups} from './vendor/useCandidateGroups'
import {post,searchError} from './api'
let app: ReturnType<typeof createApp> | null = null
function mount() {
const el = document.getElementById('orbit-search')
if (!el || el.hasAttribute('data-mounted')) return
el.setAttribute('data-mounted','true')
app = createApp({setup() {
  const s=useMetadataSearch()
  const title=ref(new URLSearchParams(location.search).get('q') || '')
  const author=ref(''), isbn=ref(''), language=ref('en'), notes=ref('')
  const medium=ref<any>('ebook'), searchedMedium=ref<any>('ebook')
  const open=ref(''), busy=ref(''), message=ref('')
  const editions=ref<Record<string,string>>({}),covers=ref<Record<string,string>>({})
  const availability=ref<Record<string,any>>({})
  const coverOrder=computed(()=>searchedMedium.value==='audiobook'?s.audioCoverProviderOrder.value:s.coverProviderOrder.value)
  const {groups}=useCandidateGroups(s.filteredResults,searchedMedium,(c:any)=>availability.value[c._token]??null,coverOrder,language,s.resultProviderOrder)
  const selected=(g:any)=>g.isbnChoices.find((c:any)=>c.isbn===editions.value[g.key]) || (editions.value[g.key]==='title'?null:g.recommendedIsbnChoice)
  async function loadAvailability(){
    const tokens=s.results.value.map((c:any)=>c._token).filter(Boolean)
    if(!tokens.length) return
    try { availability.value=await post('availability',{tokens}) } catch(e:any){message.value=e.message}
  }
  async function search(e?:Event){
    e?.preventDefault(); if(!title.value.trim()&&!author.value.trim()&&!isbn.value.trim())return
    searchedMedium.value=medium.value;searchError.value='';message.value='';open.value='';availability.value={}
    await s.search({title:title.value.trim(),author:author.value.trim(),isbn:isbn.value.trim(),mediaKind:medium.value})
    await loadAvailability()
  }
  async function retry(p:any){searchError.value='';await s.retryProvider(p);await loadAvailability()}
  async function requestBook(g:any){
    busy.value=g.key;message.value=''
    const choice=selected(g),c=choice?.candidate||g.candidate
    try {
      const out=await post('request',{token:c._token,tokens:g.candidates.map((m:any)=>m._token),cover:covers.value[g.key]||g.coverUrl,language:language.value,notes:notes.value,isbn:choice?.isbn||null})
      location.assign(out.url)
    } catch(e:any){message.value=e.message; await loadAvailability()} finally{busy.value=''}
  }
  onMounted(async()=>{try{await s.loadProviders();if(title.value)await search()}catch{}})
  const input=(label:string,r:any,placeholder='',props={})=>h('label',{class:'orbit-field'},[h('span',label),h('input',{value:r.value,placeholder,...props,onInput:(e:any)=>r.value=e.target.value})])
  const button=(text:string,fn:any,props={})=>h('button',{type:'button',onClick:fn,...props},text)
  return()=>h('div',{class:'orbit'},[
    h('header',[h('h1','Find your next book'),h('p','Search books and audiobooks, compare editions, and request them in Shelfarr.')]),
    h('form',{onSubmit:search},[
      h('div',{class:'orbit-tabs',role:'group','aria-label':'Book format'},[['ebook','Ebooks'],['audiobook','Audiobooks'],['comic','Comics & manga']].map(([v,l])=>button(l,()=>{medium.value=v;if(s.hasSearched.value)search()}, {'aria-pressed':medium.value===v,class:medium.value===v?'selected':''}))),
      h('div',{class:'orbit-fields'},[input('Title',title,'The Three-Body Problem',{maxlength:500}),input('Author',author,'Cixin Liu',{maxlength:255}),input('ISBN',isbn,'Optional',{maxlength:32})]),
      h('div',{class:'orbit-actions'},[input('Language',language,'en',{maxlength:12}),h('button',{type:'submit',class:'primary',disabled:s.isStreaming.value},s.isStreaming.value?'Searching…':'Search')]),
      h('div',{class:'orbit-providers','aria-label':'Metadata providers'},s.providers.value.map(p=>button(`${p.label}${s.providerCounts[p.key]?` · ${s.providerCounts[p.key]}`:''}`,()=>s.toggleProvider(p.key),{'aria-pressed':s.selectedProviders.value.includes(p.key),class:s.selectedProviders.value.includes(p.key)?'selected':''})))
    ]),
    searchError.value?h('p',{role:'alert',class:'orbit-alert'},searchError.value):null,
    message.value?h('p',{role:'alert',class:'orbit-alert'},message.value):null,
    ...s.interruptedProviders.value.map(p=>h('p',{class:'orbit-alert'},[`${s.providers.value.find(x=>x.key===p.provider)?.label||p.provider}: ${p.outcome}. `,button(s.retryingProviders.value.includes(p.provider)?'Retrying…':'Retry',()=>retry(p.provider),{disabled:s.retryingProviders.value.includes(p.provider)})])),
    s.hasSearched.value?h('p',{role:'status'},`${groups.value.length} works${s.isStreaming.value?' · Still searching…':''}`):null,
    !s.isStreaming.value&&s.hasSearched.value&&!groups.value.length&&!searchError.value?h('p','No matches. Try a shorter title, an author, or an ISBN.'):null,
    h('div',{class:'orbit-results'},groups.value.map(g=>{
      const choice=selected(g),available=g.availability?.ownedBookId,existing=g.availability?.existingRequestId
      return h('article',{key:g.key,class:'orbit-work'},[
        h('div',{class:'orbit-work-main'},[
          (covers.value[g.key]||g.coverUrl)?h('img',{class:'orbit-cover',src:covers.value[g.key]||g.coverUrl,alt:`Cover of ${g.title}`,loading:'lazy',referrerpolicy:'no-referrer'}):h('div',{class:'orbit-cover placeholder'},'No cover'),
          h('div',{class:'orbit-info'},[h('h2',g.title),h('p',g.authors.join(', ')),h('p',{class:'orbit-muted'},[searchedMedium.value==='audiobook'?'Audiobook':searchedMedium.value==='comic'?'Comic':'Ebook',g.publishedYear,`${g.providers.length} source${g.providers.length===1?'':'s'}`].filter(Boolean).join(' · ')),h('p',{class:'orbit-muted'},g.providers.map(p=>s.providers.value.find(x=>x.key===p)?.label||p).join(' · ')),button(open.value===g.key?'Hide editions':'Editions & details',()=>open.value=open.value===g.key?'':g.key)]),
          h('div',{class:'orbit-request'},[available?h('span',{class:'orbit-owned'},'In your library'):existing?h('a',{href:`/requests/${existing}`},'View request'):button(busy.value===g.key?'Requesting…':`Request ${searchedMedium.value==='audiobook'?'audiobook':searchedMedium.value==='comic'?'comic':'ebook'}`,()=>requestBook(g),{class:'primary',disabled:!!busy.value||s.isStreaming.value}),!available&&!existing?h('small',choice?`ISBN ${choice.isbn}`:'Match by title & author'):null])
        ]),
        open.value===g.key?h('div',{class:'orbit-details'},[
          g.candidate.description?h('p',{class:'orbit-description'},g.candidate.description.replace(/<[^>]*>/g,'')):null,
          h('label',{class:'orbit-field'},[h('span','Edition'),h('select',{value:editions.value[g.key]||(g.recommendedIsbnChoice?.isbn??'title'),onChange:(e:any)=>editions.value[g.key]=e.target.value},[...g.isbnChoices.map(c=>h('option',{value:c.isbn},`${c.isbn} · ${c.candidate.language||'Language unknown'} · ${c.candidate.publishedYear||'Year unknown'} · ${c.providers.join(', ')}${g.recommendedIsbnChoice===c?' · Recommended':''}`)),h('option',{value:'title'},'Match by title & author')])]),
          g.coverUrls.length>1?h('div',{class:'orbit-covers','aria-label':'Choose cover'},g.coverUrls.map((url:string,i:number)=>h('button',{type:'button','aria-label':`Select cover ${i+1}`,'aria-pressed':(covers.value[g.key]||g.coverUrl)===url,onClick:()=>covers.value[g.key]=url},[h('img',{src:url,alt:`Cover option ${i+1}`,loading:'lazy',referrerpolicy:'no-referrer'})]))):null,
          input('Request notes',notes,'Optional',{maxlength:2000})
        ]):null
      ])
    })),
    h('footer',[h('span','Search by BookOrbit · '),h('a',{href:'/search/orbit/source'},'Integration source & licenses')])
  ])
}});app.mount(el)
}
mount()
document.addEventListener('turbo:load',mount)
document.addEventListener('turbo:before-cache',()=>{app?.unmount();app=null;document.getElementById('orbit-search')?.removeAttribute('data-mounted')})
