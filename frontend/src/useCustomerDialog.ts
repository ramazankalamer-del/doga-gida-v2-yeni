import {useEffect,useRef} from 'react';

export function useCustomerDialog(onClose:()=>void,busy=false){
 const ref=useRef<HTMLElement>(null),close=useRef(onClose),blocked=useRef(busy);
 close.current=onClose;blocked.current=busy;
 useEffect(()=>{
  const previous=document.activeElement;
  const dialog=ref.current;
  dialog?.querySelector<HTMLElement>('button,input,select,a[href]')?.focus();
  const keydown=(e:KeyboardEvent)=>{
   if(e.key==='Escape'){e.preventDefault();e.stopPropagation();if(!blocked.current)close.current();}
   if(e.key==='Tab'&&dialog){
    const controls=[...dialog.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),a[href]')].filter(el=>el.getClientRects().length);
    const first=controls[0],last=controls.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
   }
  };
  document.addEventListener('keydown',keydown);
  return()=>{document.removeEventListener('keydown',keydown);if(previous instanceof HTMLElement&&previous.isConnected)previous.focus();};
 },[]);
 return ref;
}
