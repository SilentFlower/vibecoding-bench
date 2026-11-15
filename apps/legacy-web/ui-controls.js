/** 原生页面复用控件：保留原表单字段、校验与change事件。 */
(() => {
  let current=null,sequence=0;
  const selects=new Map(),times=new Map();
  /** 同步菜单文本与原生禁用状态。@param {HTMLSelectElement} select 原字段。@return {void} */
  function sync(select){const trigger=selects.get(select);if(!trigger)return;const option=select.selectedOptions[0];trigger.textContent=option?.textContent||'暂无选项';if(trigger.disabled!==(select.disabled||!select.options.length))trigger.disabled=select.disabled||!select.options.length;trigger.setAttribute('aria-required',String(select.required));}
  /** 关闭当前菜单并可选恢复焦点。@param {boolean} focus 是否返回触发器。@return {void} */
  function close(focus=true){if(!current)return;const {trigger,popup}=current;current=null;trigger.setAttribute('aria-expanded','false');popup.remove();if(focus&&trigger.isConnected)trigger.focus({preventScroll:true});}
  /** 打开来自实际option的候选，所有选择提交原始业务值。@param {HTMLSelectElement} select 原字段。@return {void} */
  function open(select){
    const trigger=selects.get(select);if(!trigger||trigger.disabled)return;
    if(current?.select===select){close();return;}close(false);
    const popup=document.createElement('div');popup.className='native-choice-popup';popup.id='native-choice-'+(++sequence);popup.setAttribute('role','listbox');popup.tabIndex=-1;
    trigger.setAttribute('aria-controls',popup.id);trigger.setAttribute('aria-expanded','true');
    const options=document.createElement('div');options.className='native-choice-options';popup.append(options);
    const paint=query=>{options.replaceChildren();for(const option of select.options){if(option.hidden||!option.textContent.toLowerCase().includes(query.toLowerCase()))continue;const node=document.createElement('button');node.type='button';node.className='native-choice-option';node.setAttribute('role','option');node.setAttribute('aria-selected',String(option.selected));node.disabled=option.disabled;node.textContent=option.textContent;node.onclick=()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));sync(select);close();};options.append(node);}if(!options.children.length){const empty=document.createElement('p');empty.textContent='没有匹配的选项';options.append(empty);}};
    paint('');
    let search=null;
    if(select.options.length>8){search=document.createElement('input');search.type='search';search.className='native-choice-search';search.placeholder='搜索选项';search.setAttribute('aria-label','搜索'+(select.getAttribute('aria-label')||select.name||'选项'));search.oninput=()=>paint(search.value);popup.prepend(search);}
    const portal=trigger.closest('.modal')||document.body;portal.append(popup);
    const rect=trigger.getBoundingClientRect(),width=Math.min(Math.max(rect.width,180),innerWidth-24);popup.style.width=width+'px';popup.style.left=Math.max(12,Math.min(rect.left,innerWidth-width-12))+'px';popup.style.maxHeight=Math.max(120,Math.min(320,innerHeight-24))+'px';
    const below=innerHeight-rect.bottom;popup.style.top=(below>=Math.min(320,popup.scrollHeight)+8?rect.bottom+6:Math.max(12,rect.top-popup.offsetHeight-6))+'px';
    current={select,trigger,popup};
    popup.onkeydown=event=>{if(!['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(event.key)||event.target===search&&!['ArrowDown','ArrowUp'].includes(event.key))return;const nodes=[...options.querySelectorAll('button:not(:disabled)')];if(!nodes.length)return;event.preventDefault();const index=nodes.indexOf(document.activeElement);if(event.key==='Enter'||event.key===' '){nodes[Math.max(0,index)].click();return;}const next=event.key==='Home'?0:event.key==='End'?nodes.length-1:event.key==='ArrowUp'?(index<=0?nodes.length-1:index-1):(index+1)%nodes.length;nodes[next].focus();};
    (search||options.querySelector('[aria-selected=true]:not(:disabled)')||options.querySelector('button:not(:disabled)')||popup).focus({preventScroll:true});
  }
  /** 编辑HH:mm草稿，确认才写入原字段。@param {HTMLInputElement} source 原时间字段。@return {void} */
  function openTime(source){
    const trigger=times.get(source);if(!trigger||source.disabled)return;
    close(false);const popup=document.createElement('div');popup.className='native-choice-popup native-time-popup';popup.setAttribute('role','dialog');popup.setAttribute('aria-label','选择时间');
    const title=document.createElement('strong');title.textContent='选择时间';popup.append(title);
    const fields=document.createElement('div');fields.className='native-time-fields';popup.append(fields);
    const values=(source.value||'00:00').split(':'),inputs=[];
    for(const [index,label,max] of [[0,'小时',23],[1,'分钟',59]]){const field=document.createElement('label');field.textContent=label;const input=document.createElement('input');input.type='number';input.min='0';input.max=String(max);input.step='1';input.required=true;input.value=String(Number(values[index]));input.setAttribute('aria-label',label);field.append(input);fields.append(field);inputs.push(input);}
    const footer=document.createElement('div');footer.className='native-time-footer';popup.append(footer);
    const cancel=document.createElement('button');cancel.type='button';cancel.textContent='取消';cancel.onclick=()=>close();footer.append(cancel);
    const apply=document.createElement('button');apply.type='button';apply.textContent='确定';apply.onclick=()=>{for(const input of inputs){if(!input.reportValidity())return;}source.value=inputs.map(input=>input.value.padStart(2,'0')).join(':');source.dispatchEvent(new Event('input',{bubbles:true}));source.dispatchEvent(new Event('change',{bubbles:true}));trigger.textContent=source.value;close();};footer.append(apply);
    (trigger.closest('.modal')||document.body).append(popup);const rect=trigger.getBoundingClientRect();popup.style.width=Math.min(290,innerWidth-24)+'px';popup.style.left=Math.max(12,Math.min(rect.left,innerWidth-302))+'px';popup.style.top=(innerHeight-rect.bottom>230?rect.bottom+6:Math.max(12,rect.top-230))+'px';
    current={trigger,popup};trigger.setAttribute('aria-expanded','true');enhance();inputs[0].focus();
  }
  /** 增强新增字段，原生name/value与校验约束持续有效。@param {ParentNode} root 字段范围。@return {void} */
  function enhance(root=document){
    for(const input of root.querySelectorAll('input[type=number]:not([data-native-number])')){
      if(input.closest('[data-vue-managed],.fui-field'))continue;
      input.dataset.nativeNumber='true';const fieldLabel=input.getAttribute('aria-label')||input.closest('label')?.querySelector('.lbl')?.textContent?.trim()||input.name||'数值';if(!input.hasAttribute('aria-label'))input.setAttribute('aria-label',fieldLabel);const wrapper=document.createElement('div');wrapper.className='native-number';input.before(wrapper);wrapper.append(input);const steps=document.createElement('span');steps.className='native-number-steps';wrapper.append(steps);
      for(const [direction,label] of [[-1,'减少'],[1,'增加']]){const button=document.createElement('button');button.type='button';button.dataset.direction=String(direction);button.textContent=direction<0?'−':'+';button.setAttribute('aria-label',label+(input.getAttribute('aria-label')||input.name||'数值'));button.onclick=()=>{if(input.disabled||input.readOnly)return;input.stepUp(direction);input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));};steps.append(button);}
    }
    for(const select of root.querySelectorAll('select:not([multiple]):not([data-native-choice]):not([aria-hidden=true])')){
      if(select.hidden||select.closest('[hidden],[data-vue-managed],.fui-field'))continue;
      select.dataset.nativeChoice='true';select.classList.add('native-choice-source');select.setAttribute('aria-hidden','true');select.tabIndex=-1;const trigger=document.createElement('button');trigger.type='button';trigger.className='native-choice-trigger';trigger.setAttribute('role','combobox');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-label',select.getAttribute('aria-label')||select.closest('label')?.querySelector('.lbl')?.textContent||select.name||'选择');select.after(trigger);selects.set(select,trigger);trigger.onclick=()=>open(select);trigger.onkeydown=event=>{if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();open(select);}};select.addEventListener('change',()=>sync(select));select.addEventListener('invalid',event=>{event.preventDefault();trigger.focus();});sync(select);
    }
    for(const source of root.querySelectorAll('input[type=time]:not([data-native-time])')){
      if(source.closest('[data-vue-managed],.fui-field'))continue;
      source.dataset.nativeTime='true';source.classList.add('native-time-source');source.setAttribute('aria-hidden','true');source.tabIndex=-1;
      const trigger=document.createElement('button');trigger.type='button';trigger.className='native-choice-trigger native-time-trigger';trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-label',source.getAttribute('aria-label')||source.closest('label')?.firstChild?.textContent?.trim()||'选择时间');source.after(trigger);times.set(source,trigger);trigger.onclick=()=>openTime(source);source.addEventListener('invalid',event=>{event.preventDefault();trigger.focus();});source.addEventListener('change',()=>{trigger.textContent=source.value||'选择时间';});
    }
    for(const [source,trigger] of times){if(!source.isConnected){times.delete(source);continue;}trigger.textContent=source.value||'选择时间';if(trigger.disabled!==source.disabled)trigger.disabled=source.disabled;}
    for(const [select] of selects){if(!select.isConnected){selects.delete(select);continue;}sync(select);}
    for(const input of document.querySelectorAll('[data-native-number]'))for(const button of input.parentElement.querySelectorAll('button')){const value=input.valueAsNumber,limited=input.value!==''&&Number.isFinite(value)&&(Number(button.dataset.direction)<0?input.min!==''&&value<=Number(input.min):input.max!==''&&value>=Number(input.max));const disabled=input.disabled||input.readOnly||limited;if(button.disabled!==disabled)button.disabled=disabled;}
  }
  document.addEventListener('keydown',event=>{if(current&&event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close();}},true);
  document.addEventListener('pointerdown',event=>{if(current&&!current.popup.contains(event.target)&&!current.trigger.contains(event.target))close(false);},true);
  document.addEventListener('input',event=>{if(event.target.matches('[data-native-number]'))enhance();});
  document.addEventListener('reset',()=>queueMicrotask(()=>enhance()));
  window.addEventListener('hashchange',()=>close(false));
  window.addEventListener('resize',()=>close(false));
  document.addEventListener('scroll',event=>{if(current&&!current.popup.contains(event.target))close(false);},true);
  const scrollTimers=new Map();
  // 只在实际滚动时显示滚动条，轨道宽度固定以避免内容跳动。
  document.addEventListener('scroll',event=>{const target=event.target===document?document.documentElement:event.target;if(!(target instanceof HTMLElement))return;clearTimeout(scrollTimers.get(target));target.dataset.activeScroll='';scrollTimers.set(target,setTimeout(()=>{delete target.dataset.activeScroll;scrollTimers.delete(target);},800));},true);
  window.addEventListener('pagehide',()=>{for(const [target,timer] of scrollTimers){clearTimeout(timer);delete target.dataset.activeScroll;}scrollTimers.clear();});

  let scheduled=false;
  new MutationObserver(records=>{if(!records.some(record=>record.type==='attributes'||record.target.matches?.('select,option')||[...record.addedNodes].some(node=>node.nodeType===1&&(node.matches('input,select,option')||node.querySelector('input,select')))))return;if(!scheduled){scheduled=true;requestAnimationFrame(()=>{scheduled=false;enhance();});}}).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','readonly']});
  window.enhanceRuntimeControls=enhance;
  enhance();
})();
