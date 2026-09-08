import {useEffect,useState} from 'react';
export async function request(path, options={}) {
  const response=await fetch(`/api${path}`,options);
  if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{}throw new Error(typeof detail==='string'?detail:`Request failed (${response.status}). Try again.`);}
  return response.json();
}
export function useApi(path){
  const [state,setState]=useState({loading:true});
  useEffect(()=>{const controller=new AbortController();setState({loading:true});request(path,{signal:controller.signal}).then(data=>setState({data,loading:false})).catch(error=>{if(error.name!=='AbortError')setState({error:error.message,loading:false});});return()=>controller.abort();},[path]);
  return state;
}
