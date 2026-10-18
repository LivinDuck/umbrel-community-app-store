import {ref} from 'vue'
export const searchError = ref('')
export async function api(path: string, options: RequestInit = {}) {
  const target = path.replace('/api/v1/metadata-fetch/', '/search/orbit/')
  const res = await fetch(target, {...options, credentials:'same-origin'})
  if (!res.ok) {
    searchError.value = res.status === 401 ? 'Your session expired. Reload this page.' : 'BookOrbit search is unavailable. Check that BookOrbit is running, then try again.'
    throw new Error(searchError.value)
  }
  return res
}
export async function post(path: string, body: unknown) {
  const res = await fetch('/search/orbit/'+path, {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content || ''},body:JSON.stringify(body)})
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || data.errors?.join('; ') || 'Request failed')
  return data
}
