/* adjustable-bed-card 5.0.0b8 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var vi=Object.defineProperty;var bi=Object.getOwnPropertyDescriptor;var T=(o,s,e,t)=>{for(var i=t>1?void 0:t?bi(s,e):s,n=o.length-1,r;n>=0;n--)(r=o[n])&&(i=(t?r(s,e,i):r(i))||i);return t&&i&&vi(s,e,i),i};function Se(o,s,e=o?.entities[s]?.device_id){let t=o?.states[s]?.attributes,i=t?.hold_lease_mode;if(i!=="stream"&&i!=="latched"||!e)return;let n=t?.hold_lease_motor,r=t?.bed_side;return{deviceId:e,...typeof n=="string"&&n?{motor:n}:{},...r==="left"||r==="right"||r==="both"?{side:r}:{}}}function ke(o,s){return o.holdLease?o.heldControls?.[s]??o.heldControl?!!o.deviceId:!!(o.timedMove??o.holdLease.motor):!1}var yi=3e4;function yt(o,s){return!(o.heldControls?.[s]??o.heldControl)||ke(o,s)}function wt(o,s,e,t){if(!ke(s,e)||!s.holdLease)return;if(s.heldControls?.[e]??s.heldControl)return Ve(o,s,e,t);let i=s.timedMove??{deviceId:s.holdLease.deviceId,motor:s.holdLease.motor,side:s.holdLease.side};return o?.callService("adjustable_bed","timed_move",{device_id:i.deviceId,...i.side?{side:i.side}:{},motor:i.motor,direction:e,duration_ms:750,hold_owner:t.owner,hold_generation:t.generation})}function Ke(o,s){let e=o?.entities[s],i=o?.states[s]?.attributes?.hold_release_button_key;if(!(!e?.device_id||typeof i!="string"))return Object.values(o?.entities??{}).find(n=>n.device_id===e.device_id&&n.entity_id.startsWith("button.")&&n.translation_key===i)?.entity_id}function $t(o,s){let e=o?.entities[s]?.device_id,t=o?.states[s]?.attributes,i=t?.held_control,n=t?.hold_start_delay_ms,r=t?.hold_release_delay_ms;if(!e||typeof i!="string"||typeof n!="number"||!Number.isFinite(n)||n<0||typeof r!="number"||!Number.isFinite(r)||r<0)return;let l=Ke(o,s);if(typeof t?.hold_release_button_key=="string"&&!l)return;let a=Se(o,s,e);return{...l?{releaseButton:l}:{},...a?{holdLease:a}:{},key:s,up:s,deviceId:e,holdEntityId:s,heldControl:{control:i,startDelayMs:n,releaseDelayMs:r}}}function Ue(o,s,e){if(s.timedMove)return o?.callService("adjustable_bed","timed_move",{device_id:s.timedMove.deviceId,...s.timedMove.side?{side:s.timedMove.side}:{},motor:s.timedMove.motor,direction:e,duration_ms:1e3});if(s.cover)return o?.callService("cover",e==="up"?"open_cover":"close_cover",{entity_id:s.cover});let t=e==="up"?s.up:s.down;return t?o?.callService("button","press",{entity_id:t}):void 0}function Ve(o,s,e,t){let i=s.heldControls?.[e]??s.heldControl;if(!i||!s.deviceId)return;let n=o?.states[s.holdEntityId??s.cover??""]?.attributes.bed_side,r={device_id:[s.deviceId],control:i.control,duration:t?750/1e3:60,...t?{hold_owner:t.owner,hold_generation:t.generation}:{}};return(n==="left"||n==="right"||n==="both")&&(r.side=n),o?.callService("adjustable_bed","hold_control",r)}function xt(o,s,e){Ue(o,s,e)?.catch(()=>{})}function kt(o,s,e,t){let i=()=>t(),n=()=>{e()&&t()};o.addEventListener("blur",i),s.addEventListener("visibilitychange",n);let r=!0;return()=>{r&&(r=!1,o.removeEventListener("blur",i),s.removeEventListener("visibilitychange",n))}}function Et(o,s){let e=s[o]?.parent_device_id??s[o]?.via_device_id;return e&&s[e]?e:void 0}function wi(o,s){return Object.values(s).some(e=>(e.parent_device_id??e.via_device_id)===o)}function xe(o,s){let e=o.states[s]?.attributes,t=e?.bed_side??e?.side,i=t==="left"||t==="right"||t==="both"?t:void 0,n=o.entities[s]?.translation_key==="stop_both"?"both":void 0;if(!(i&&n&&i!==n))return i??n}function bt(o,s){let e=o.entities[s];return e?.platform==="adjustable_bed"&&s.startsWith("button.")&&(e.translation_key==="stop"||e.translation_key==="stop_both")}function Q(o,s){if(!o||!s)return;let e=o.entities[s]?.device_id;if(!e)return;let t=o.devices??{},i=Et(e,t),n=xe(o,s)??(!i&&wi(e,t)?"both":void 0);return{deviceId:i&&n?i:e,side:n,physicalDeviceId:e,...i?{parentDeviceId:i}:{},...n==="both"?{physicalChildIds:Object.entries(t).filter(([,r])=>(r.parent_device_id??r.via_device_id)===e).map(([r])=>r)}:{}}}function $i(o,s){return(o.parentDeviceId??o.deviceId)!==(s.parentDeviceId??s.deviceId)?!1:o.side==="both"||s.side==="both"?!0:o.side&&s.side?o.side===s.side:!o.physicalDeviceId||!s.physicalDeviceId||o.physicalDeviceId===s.physicalDeviceId}function We(o,s){if(!o||!s)return[];let e=o.entities[s]?.device_id;if(!e)return[];let t=xe(o,s);if(t==="left"||t==="right"){let p=t==="left"?"right":"left",h=Object.values(o.entities).filter(u=>u.entity_id!==s&&u.device_id===e&&bt(o,u.entity_id)&&xe(o,u.entity_id)===p);if(h.length===1)return[h[0].entity_id]}let i=o.devices??{},n=Et(e,i);if(!n)return[];let r=Object.entries(i).filter(([,p])=>(p.parent_device_id??p.via_device_id)===n).map(([p])=>p);if(r.length!==2||!r.includes(e))return[];let l=r.find(p=>p!==e),a=Object.values(o.entities).filter(p=>{if(p.device_id!==l||!bt(o,p.entity_id))return!1;let h=xe(o,p.entity_id);return h!=="both"&&(h===void 0||h!==t)});return a.length===1?[a[0].entity_id]:[]}function $e(o){let s=o.holdEntityId??o.cover??o.up??o.down??"";return`${o.key}\0${s}`}var Ee=class{constructor(s,e={setTimeout:(t,i)=>globalThis.setTimeout(t,i),clearTimeout:t=>globalThis.clearTimeout(t)}){this.actions=s;this.timers=e;this._key=null;this._motor=null;this._scopeStops=[];this._remainingStops=[];this._stopTargetGenerations=new Map;this._keyboardKey=null;this._motorId=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0;this._repeatBlocked=!1;this._tapDirection=null;this._leaseOwner=`card-${Math.random().toString(36).slice(2,12)}`;this._started=!1;this._releaseId=0;this._pendingReleases=new Map}get heldKey(){return this._key}start(s,e,t,i,n=i?[i]:[],r=[],l=null,a){if(this._key!==null)return;let p=Array.isArray(n)?n:[];this._target=Array.isArray(n)?a:n,this._flushPendingForTarget(i??s.cover??s.key),this._key=s.key,this._motor=Object.freeze({...s,...s.timedMove?{timedMove:Object.freeze({...s.timedMove})}:{}}),this._motorId=$e(s),this._cover=s.cover??null,this._stop=i??null,this._scopeStops=[...new Set([...p,...i?[i]:[],...s.cover?[s.cover]:[],...this._targetScope(this._target)])],this._remainingStops=[...new Set(r)],this.claimStopScope(this._scopeStops),this._pointerId=t,this._keyboardKey=l;let h=++this._generation;this._heldControl=s.heldControls?.[e]??s.heldControl,this._releaseButton=s.releaseButton;let u=this.actions.lease!==void 0&&ke(s,e);if(this._heldControl){let m=this._heldControl.startDelayMs;m<=0?this._startHeldControl(this._motor,e,h,u):this._startTimer=this.timers.setTimeout(()=>this._startHeldControl(this._motor??s,e,h,u),m);return}this._started=!0,u?this._leaseHold(this._motor,e,h):this._repeat(this._motor,e,h)}get tapMoving(){return this._tapDirection!==null}tapDirection(s){return this._tapDirection!==null&&this._motorId===$e(s)?this._tapDirection:void 0}tap(s,e,t,i=t?[t]:[],n=[],r){if(this._tapDirection!==null){this.endTap();return}if(this._key!==null||(s.heldControls?.[e]??s.heldControl)&&!(this.actions.lease&&ke(s,e))||(this._tapDirection=e,this.start(s,e,null,t,i,n,null,r),this._tapDirection===null))return;let a=this._generation;this._tapTimer=this.timers.setTimeout(()=>{a===this._generation&&this.endTap()},yi),this.actions.changed?.()}endTap(){this._tapDirection!==null&&this._motor&&this.end(this._motor)}retireTap(){this._tapDirection!==null&&this._reset()}_targetScope(s){if(!s)return[];let e=s.side==="left"||s.side==="right"?[s.side]:["left","right"];return[...new Set([s.deviceId,...s.physicalDeviceId?[s.physicalDeviceId]:[],...s.physicalChildIds??[]])].flatMap(i=>e.map(n=>`target:${i}:${n}`))}claimStopScope(s,e){for(let t of new Set([...s,...this._targetScope(e)]))this._stopTargetGenerations.set(t,(this._stopTargetGenerations.get(t)??0)+1)}_startHeldControl(s,e,t,i){this._startTimer=void 0,!(t!==this._generation||this._motorId!==$e(s))&&(this._started=!0,i?this._leaseHold(s,e,t):this._holdControl(s,e,t))}_leaseHold(s,e,t){let i={owner:this._leaseOwner,generation:t},n=!0,r=()=>{n=!1,t===this._generation&&(this._renewTimer!==void 0&&(this.timers.clearTimeout(this._renewTimer),this._renewTimer=void 0),this.retireTap())},l=this.actions.lease?.(s,e,i);if(!l)return;l.then(r,r);let a=()=>{this._renewTimer=void 0,!(!n||t!==this._generation||this._repeatBlocked)&&(this.actions.lease?.(s,e,i)?.catch(r),this._renewTimer=this.timers.setTimeout(a,250))};this._renewTimer=this.timers.setTimeout(a,250)}async _holdControl(s,e,t){try{let i=this.actions.holdControl?.(s,e);i&&await i}catch{}finally{t===this._generation&&this._reset()}}async _repeat(s,e,t){let i=this._motor;if(i)try{for(;t===this._generation&&!this._repeatBlocked;){let n=this.actions.pulse(i,e);if(!n)return;this._pulseInFlight=n;try{await n}finally{this._pulseInFlight===n&&(this._pulseInFlight=void 0)}}}catch{}finally{t===this._generation&&this.retireTap()}}_targetKey(s=this._stop??void 0,e=this._cover??void 0){return s??e??this._key??""}_release(s){return s.releaseButton?(this.actions.stopBed(s.releaseButton),s.releaseButton):s.cover?(this.actions.stopCover(s.cover,s.stopEntityId),s.cover):(this.actions.stopBed(s.stopEntityId),s.stopEntityId)}_scheduleRelease(){let s={id:++this._releaseId,releaseButton:this._releaseButton,motorKey:this._key??"",targetKey:this._targetKey(),target:this._target,cover:this._cover??void 0,stopEntityId:this._stop??void 0,scopeGenerations:new Map(this._scopeStops.map(t=>[t,this._stopTargetGenerations.get(t)??0]))};this._pendingReleases.set(s.id,s);let e=this._heldControl?.releaseDelayMs??0;if(e<=0){this._runRelease(s);return}s.timer=this.timers.setTimeout(()=>this._runRelease(s),e)}_runRelease(s){if(this._pendingReleases.delete(s.id)&&(s.timer!==void 0&&this.timers.clearTimeout(s.timer),[...s.scopeGenerations].every(([e,t])=>this._stopTargetGenerations.get(e)===t)))return this._release(s)}_flushPendingForTarget(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s&&(this._runRelease(t),e.add(i))}return e}_flushAllReleases(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s?(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer)):(this._runRelease(t),e.add(i))}return e}_targetsOverlap(s,e,t,i){return t!==void 0&&s===t?!0:!!e&&!!i&&$i(e,i)}_discardReleasesOverlapping(s,e){let t=!1;for(let i of[...this._pendingReleases.values()])!i.scopeGenerations.has(s)&&!this._targetsOverlap(i.targetKey,i.target,s,e)||(this._pendingReleases.delete(i.id),i.timer!==void 0&&this.timers.clearTimeout(i.timer),i.target?.side==="both"&&[...i.scopeGenerations].every(([n,r])=>this._stopTargetGenerations.get(n)===r)&&(t=!0));return t}_discardAllReleases(){for(let s of this._pendingReleases.values())s.timer!==void 0&&this.timers.clearTimeout(s.timer);this._pendingReleases.clear()}endFromPointer(s,e,t,i){this._pointerId===null||e!==this._pointerId||t&&(i!==void 0&&this._stop!==i||this.end(s,i))}endActiveFromPointer(s,e){!this._motor||this._pointerId===null||this.endFromPointer(this._motor,s,e)}endKeyboard(s,e,t){this._pointerId!==null||this._tapDirection!==null||!this._motor||s&&!this._ownsRelease(s,e)||e!==void 0&&this._stop!==e||t!==void 0&&this._keyboardKey!==null&&this._keyboardKey!==t||this.end(this._motor)}end(s,e){if(!this._ownsRelease(s,e))return;let t=this._started,i=this._heldControl!==void 0,n={releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0};t&&i&&this._scheduleRelease(),this._reset(),!(!t||i)&&this._release(n)}_ownsRelease(s,e){return this._key!==s.key?!1:e===void 0?this._motorId===$e(s):this._stop===e}cancel(s,e=!1){if(!s)return!1;let t=this._key===s.key;t&&this._reset();let i=!1;if(e)for(let n of[...this._pendingReleases.values()])n.motorKey===s.key&&(this._pendingReleases.delete(n.id),n.timer!==void 0&&this.timers.clearTimeout(n.timer),i=!0);return t||i}stopCover(s,e,t,i,n=[]){let r=s.cover;if(!r)return;let l=e!==void 0&&e.side!=="both",a=new Set,p=new Map,h,u=b=>{for(let E of b)E!==i&&(a.add(E),p.set(E,this._stopTargetGenerations.get(E)??0))};if(this._key!==null&&(t==="side"||this._key===s.key)&&(r===this._cover||i!==void 0&&this._scopeStops.includes(i)||this._targetsOverlap(this._targetKey(),this._target,r,e))){let b=this._target?.side==="both"&&l||i!==void 0&&this._remainingStops.includes(i);this._started&&b&&(i&&u(this._remainingStops),this._heldControl&&u(n)),h=this._pulseInFlight,b&&!this._heldControl&&a.size===0?this._repeatBlocked=!0:this._reset()}for(let b of[...this._pendingReleases.values()]){let E=b.target?.side==="both"&&b.target.deviceId===e?.deviceId&&(e?.side==="left"||e?.side==="right");t!=="side"&&E||t!=="side"&&b.motorKey!==s.key||!(b.cover===r||i!==void 0&&b.scopeGenerations.has(i)||this._targetsOverlap(b.targetKey,b.target,r,e))||(this._pendingReleases.delete(b.id),b.timer!==void 0&&this.timers.clearTimeout(b.timer),l&&b.target?.side==="both"&&[...b.scopeGenerations].every(([_,x])=>this._stopTargetGenerations.get(_)===x)&&u(n))}let m=this._key!==null?this._stop:null,y=()=>{for(let b of a)b!==m&&(this._stopTargetGenerations.get(b)??0)===p.get(b)&&this.actions.stopBed(b)};h?h.then(y,y):y()}stopAll(s,e,t,i=[]){let n=s??this._stop??void 0,r=this._key!==null&&this._started?{releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0}:void 0,l=typeof t=="object"?t:void 0,a=typeof t=="string"?t:void 0,p=[...new Set([...Array.isArray(e)?e:n?[n]:this._scopeStops,...this._targetScope(l),...n?[n]:[]])],h=e===!0&&!l,u=a===void 0||a===this._key||n===this._cover,m=this._key!==null&&u&&(h||p.length===0||this._scopeStops.some(x=>p.includes(x))||this._targetsOverlap(this._targetKey(),this._target,n,l)),y=!1;s!==void 0&&(h?this._discardAllReleases():y=this._discardReleasesOverlapping(s,l)),y||=m&&this._started&&this._heldControl!==void 0&&this._target?.side==="both";let b=[...new Set([...m&&this._started?this._remainingStops:[],...y?i:[]])].filter(x=>!p.includes(x)&&x!==this._stop),E=m?this._pulseInFlight:void 0,_=new Map(b.map(x=>[x,this._stopTargetGenerations.get(x)??0]));if(m&&this._reset(),s===void 0){let x=this._flushAllReleases(),C=r?.stopEntityId??r?.cover;r&&(C===void 0||!x.has(C))?this._release(r):!r&&x.size===0&&this.actions.stopBed(n)}else this.actions.stopBed(s);if(b.length>0){let x=()=>{for(let C of b)(this._stopTargetGenerations.get(C)??0)===_.get(C)&&this.actions.stopBed(C)};E?E.then(x,x):x()}}abandon(){let s=this._key===null?null:{releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0},e=this._started;this._reset();let t=new Set,i=n=>{n!==void 0&&t.add(n)};s&&e&&i(this._release(s));for(let n of[...this._pendingReleases.values()])i(this._runRelease(n));return[...t]}releaseOnFocusLoss(){this.abandon()}cancelForStopScope(s){let e=!1;for(let t of[...this._pendingReleases.values()])s.includes(t.targetKey)&&(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer),e=!0);return this._key!==null&&this._scopeStops.some(t=>s.includes(t))&&(this._reset(),e=!0),e}_reset(){this._startTimer!==void 0&&this.timers.clearTimeout(this._startTimer),this._startTimer=void 0,this._renewTimer!==void 0&&this.timers.clearTimeout(this._renewTimer),this._renewTimer=void 0,this._tapTimer!==void 0&&this.timers.clearTimeout(this._tapTimer),this._tapTimer=void 0;let s=this._tapDirection!==null;this._tapDirection=null,this._key=null,this._motor=null,this._scopeStops=[],this._remainingStops=[],this._keyboardKey=null,this._pulseInFlight=void 0,this._motorId=null,this._cover=null,this._stop=null,this._target=void 0,this._pointerId=null,this._repeatBlocked=!1,this._started=!1,this._heldControl=void 0,this._releaseButton=void 0,this._generation++,s&&this.actions.changed?.()}};function St(o,s,e){let t=()=>{o.abandon()},i=()=>{s.visibilityState==="hidden"&&t()};return s.addEventListener("visibilitychange",i),e.addEventListener("pagehide",t),()=>{s.removeEventListener("visibilitychange",i),e.removeEventListener("pagehide",t)}}function Te(o,s,e,t,i){o.stopAll(s,e??(s?[s]:void 0),t??Q(i,s),We(i,s))}function L(o,s){let e=s?o?.devices[s]:void 0;return(e?.name_by_user||e?.name)?.trim()||void 0}function S(o,s,e=s){let t=o?.states[s];return(t?o.formatEntityName(t,{type:"entity"}):o?.entities[s]?.name)||e}function Tt(o,s){if(!s||o.length<=s.length||!o.toLowerCase().startsWith(s.toLowerCase()))return o;let e=o.slice(s.length);return/^[\s\-·:,]/.test(e)&&e.replace(/^[\s\-·:,]+/,"")||o}var O="adjustable_bed",j=["graphic","motors","firmness","presets","saved_positions","memory","lighting","massage","utility","climate","connection"],Ct=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],Mt=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_reading","preset_swing","preset_incline","preset_both_up","preset_yoga"],xi=new Set(["elevate_both","starcode_m1x12_part_1","starcode_m1x12_part_2","starcode_m1x12_part_4"]),ki=o=>o.split(".",1)[0],Pt=o=>o.translation_key??"";function Ei(o,s){let e=o.states[s]?.attributes,t=e?.card_section;if(typeof t!="string")return;let{card_role:i,card_motor:n,card_slot:r}=e;return{section:t,...typeof i=="string"?{role:i}:{},...typeof n=="string"?{motor:n}:{},...typeof r=="number"?{slot:r}:{}}}var At=(o,s)=>o.states[s]?.attributes.bed_side??o.states[s]?.attributes.side;function Si(){return{motors:[],firmness:[],presets:[],presetSaves:[],memory:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[],utilityStates:[]}}function A(o,s,e){let t=Si();if(!s||!o?.entities)return t;let i=()=>t.lights.mood??={selects:[],numbers:[]},n=Object.values(o.entities).filter(v=>v.device_id===s&&v.platform===O),r=new Map,l=v=>{let g=r.get(v);return g||(g=xi.has(v)?{key:v,coverStopScope:"side"}:{key:v},r.set(v,g)),g},a=(v,g,k,w)=>{let $=l(g);$[k]=v;let re=Se(o,v,w??s);re&&($.holdLease=re);let D=o.states[v]?.attributes,Z=D?.held_control,U=D?.hold_start_delay_ms,R=D?.hold_release_delay_ms;typeof Z=="string"&&typeof U=="number"&&Number.isFinite(U)&&U>=0&&typeof R=="number"&&Number.isFinite(R)&&R>=0&&w&&($.deviceId=w,$.holdEntityId=v,$.heldControls={...$.heldControls,[k]:{control:Z,startDelayMs:U,releaseDelayMs:R}});let B=D?.paired_hold_motor;B==="back"||B==="legs"||B==="lumbar"?$.timedMove={deviceId:s,motor:B,...D?.paired_hold_side==="both"?{side:"both"}:{}}:(g==="back"||g==="legs"||g==="lumbar")&&typeof Z=="string"&&($.timedMove={deviceId:s,motor:g,...D?.bed_side==="both"?{side:"both"}:{}})},p=(v,g,k)=>{let w=l(g);w.cover=v;let $=o.states[v]?.attributes,re=$?.held_control_up,D=$?.held_control_down,Z=Ke(o,v);Z&&(w.releaseButton=Z);let U=Se(o,v,k);if(U&&(w.holdLease=U),($?.held_stop_scope==="motor"||$?.held_stop_scope==="side")&&(w.coverStopScope=$.held_stop_scope),typeof re=="string"&&typeof D=="string"&&(typeof $?.hold_release_button_key!="string"||w.releaseButton)){(g==="back"||g==="legs"||g==="lumbar")&&(w.timedMove={deviceId:s,motor:g});let R=$?.hold_start_delay_ms,B=$?.hold_release_delay_ms;($?.held_stop_scope==="motor"||$?.held_stop_scope==="side")&&k&&typeof R=="number"&&Number.isFinite(R)&&R>=0&&typeof B=="number"&&Number.isFinite(B)&&B>=0&&(w.deviceId=k,w.holdEntityId=v,w.heldControls={up:{control:re,startDelayMs:R,releaseDelayMs:B},down:{control:D,startDelayMs:R,releaseDelayMs:B}})}},h=new Map,u=v=>{let g=h.get(v);return g||(g={slot:v},h.set(v,g)),g},m=t.lights,y=[],b=[];for(let v of n){if(v.hidden)continue;let g=v.entity_id,k=Ei(o,g);if(!k||k.section==="hidden"||e&&At(o,g)!==e)continue;let w=ki(g),{role:$}=k;switch(k.section){case"motors":if($==="stop")t.stop=g;else if(w==="switch")t.synchro=g;else if(w==="select")t.controlSide=g;else{if(k.motor===void 0)break;w==="cover"?p(g,k.motor,v.device_id):$==="up"||$==="down"?a(g,k.motor,$,v.device_id):$==="reference"?l(k.motor).reference=g:$==="estimate"?l(k.motor).estimate=g:w==="sensor"&&$!=="position"?l(k.motor).angle=g:l(k.motor).position=g}break;case"firmness":t.firmness.push(g);break;case"presets":($==="save"?b:y).push({key:Pt(v),id:g});break;case"memory":if(k.slot===void 0)break;$==="save"?u(k.slot).save=g:u(k.slot).goto=g;break;case"saved_positions":w==="button"?t.estimateRemote=g:t.savedPositions=g;break;case"connection":$==="connect"?t.connect=g:$==="disconnect"?t.disconnect=g:t.connectivity=g;break;case"lighting":switch($){case"state":m.state=g;break;case"level":m.level=g;break;case"toggle":m.toggle=g;break;case"cycle":m.cycle=g;break;case"timer":m.timer=g;break;case"timer_minutes":m.timerMinutes=g,m.timerAppliesImmediately=!0;break;case"pending_timer_minutes":m.timerMinutes=g;break;case"timer_toggle":m.timerToggle=g;break;case"mood_toggle":i().toggle=g;break;case"mood":w==="select"?i().selects.push(g):w==="number"?i().numbers.push(g):(i().buttons??=[]).push(g);break;default:w==="light"?m.light=g:w==="switch"&&Pt(v)==="under_bed_lights"?m.switch=g:w==="switch"?(m.switches??=[]).push(g):w==="binary_sensor"?m.state=g:w==="sensor"?(m.states??=[]).push(g):w==="number"?(m.numbers??=[]).push(g):w==="select"?m.timer=g:(m.buttons??=[]).push(g)}break;case"massage":$==="timer"?t.massage.timer=g:w==="button"?t.massage.buttons.push(g):w==="number"?t.massage.numbers.push(g):w==="select"?(t.massage.selects??=[]).push(g):w==="switch"?(t.massage.switches??=[]).push(g):(t.massage.states??=[]).push(g);break;case"climate":w==="select"?t.climate.selects.push(g):w==="number"?t.climate.numbers.push(g):t.climate.entities.push(g);break;case"utility":w==="number"?(t.utilityNumbers??=[]).push(g):w==="select"?(t.utilitySelects??=[]).push(g):w==="sensor"||w==="binary_sensor"?(t.utilityStates??=[]).push(g):w==="switch"?(t.utilitySwitches??=[]).push(g):t.utility.push(g);break}}let E=[...r.keys()],_=[...Ct.filter(v=>r.has(v)),...E.filter(v=>!Ct.includes(v)).sort()];t.motors=_.map(v=>r.get(v)).filter(v=>v.cover||v.up||v.down||v.angle||v.position),!m.light&&!m.switch&&m.switches?.length===1&&(m.switch=m.switches[0],m.switches=void 0);let x=v=>{let g=Mt.indexOf(v);return g<0?Mt.length:g},C=v=>v.sort((g,k)=>x(g.key)-x(k.key)||(g.key<k.key?-1:g.key>k.key?1:0)||(g.id<k.id?-1:g.id>k.id?1:0)).map(g=>g.id);return t.presets=C(y),t.presetSaves=C(b),t.memory=[...h.values()].filter(v=>v.goto||v.save).sort((v,g)=>v.slot-g.slot),t}function Ce(o,s){return!s||!o?.entities?!1:Object.values(o.entities).some(e=>e.device_id===s&&e.platform===O&&o.states[e.entity_id]?.attributes.bed_side==="both")}function ae(o,s){if(!s||!o?.devices)return[];let e=i=>(L(o,i)??i).toLowerCase(),t=i=>{for(let n of Object.values(o.entities??{})){if(n.device_id!==i||n.platform!=="adjustable_bed")continue;let r=At(o,n.entity_id);if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(o.devices).filter(i=>(i.parent_device_id??i.via_device_id)===s).map(i=>i.id).sort((i,n)=>t(i)-t(n)||e(i).localeCompare(e(n)))}function Me(o,s){if(!s||!o?.devices)return s;let e=o.devices[s]?.parent_device_id??o.devices[s]?.via_device_id;return e&&o.devices[e]&&ae(o,e).length?e:s}function F(o){let s=o.lights;return o.motors.length===0&&!o.synchro&&!o.controlSide&&o.firmness.length===0&&o.presets.length===0&&o.presetSaves.length===0&&o.memory.length===0&&!o.stop&&!o.connect&&!o.disconnect&&!o.connectivity&&!le(s)&&!s.state&&o.massage.buttons.length===0&&o.massage.numbers.length===0&&!o.massage.selects?.length&&!o.massage.states?.length&&!o.massage.switches?.length&&!o.massage.timer&&o.climate.entities.length===0&&o.climate.selects.length===0&&o.climate.numbers.length===0&&o.utility.length===0&&!o.utilityNumbers?.length&&!o.utilitySelects?.length&&!o.utilityStates?.length&&!o.utilitySwitches?.length&&!o.savedPositions}function le(o){return!!(o.light||o.switch||o.switches?.length||o.level||o.toggle||o.numbers?.length||o.buttons?.length||o.states?.length||o.cycle||o.timer||o.timerMinutes||o.timerToggle||o.mood?.toggle||o.mood?.selects.length||o.mood?.numbers.length||o.mood?.buttons?.length)}var Rt={"action.on":"On","action.off":"Off","action.close":"Close","action.confirm":"{action}? This replaces the saved preset.","editor.open_dialog":"Open full card in a dialog","editor.show_percentage_graphic":"Draw percentage positions (schematic)","editor.show_lumbar_graphic":"Show a separate lumbar section","editor.show_graphic_labels":"Show labels beneath the graphic","section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.stop":"Stop","action.stop_all":"Stop all","tap.moving_up":"Moving up \xB7 tap to stop","tap.moving_down":"Moving down \xB7 tap to stop","motor.tv_lift":"TV lift","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle, reconnects when needed","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.motors_group":"Motors","editor.tap_to_move":"Tap to start and stop movement","editor.tap_to_move_hint":"Tap an arrow to start. Tap any arrow or Stop to end. Movement stops by itself after at most 30 seconds.","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Side","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"Glance only","editor.recipe_quick":"Quick actions","editor.recipe_controls":"Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Side to control","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both","section.saved_positions":"Saved positions","editor.show_saved_positions":"Saved positions","estimate.readout":"\u2248 {percent}%","estimate.readout_was":"Was \u2248 {percent}%","estimate.unknown":"Unknown","estimate.not_calibrated":"Not calibrated","estimate.chip_estimated":"Estimated","estimate.chip_unconfirmed":"Unconfirmed","estimate.chip_unknown":"Unknown","estimate.alert_calibrate":"Estimated positions are on but not calibrated yet.","estimate.calibrate_now":"Calibrate now","estimate.alert_unconfirmed":"Position unconfirmed after restart. Last estimate: {values}. Saved positions are paused until you confirm.","estimate.alert_unknown":"Position unknown: {reason}. Saved positions are paused until you set the reference.","estimate.reason_not_referenced":"no reference is set yet","estimate.reason_restart":"Home Assistant restarted","estimate.reason_failed_move":"a movement failed","estimate.reason_untracked_move":"the bed moved in a way that is not timed","estimate.reason_hardware_preset":"a hardware preset or memory moved the bed","estimate.reason_remote":"you reported using the remote","estimate.reason_connection_lost":"the connection dropped during a movement","estimate.unchanged":"It hasn't moved","estimate.set_reference":"Set reference\u2026","estimate.edit":"Edit","estimate.done":"Done","estimate.edit_hint":"Tap a position to rename, update or delete it.","estimate.save":"Save\u2026","estimate.footer":"Estimated from movement time. Remote use is not seen.","estimate.scope_both":"Both sides","estimate.scope_left":"Left only","estimate.scope_right":"Right only","estimate.recalled":"Moved to {name} (estimated)","estimate.ref_title":"Set reference","estimate.ref_text":"Choose how to get a known position. The bed never moves on its own to recover.","estimate.ref_lowering":"The lowering has finished. Check that the motors are fully lowered, then confirm.","estimate.ref_flat":"Fully lowered now","estimate.ref_flat_detail":"{motors} are fully down. Sets them to 0%.","estimate.ref_lower":"Lower fully, then I confirm","estimate.ref_lower_detail":"Moves down for the full travel time plus a margin. You confirm it is fully lowered afterwards.","estimate.ref_only":"Only the {motor}","estimate.ref_only_detail":"The other motors keep their estimate.","estimate.ref_lower_start":"Lower","estimate.ref_confirm":"Confirm fully lowered","estimate.save_title":"Save current position","estimate.name":"Name","estimate.create_button":"Also create a button entity","estimate.create_button_detail":"For automations and voice.","estimate.save_note":"Recall moves each motor for the calculated time. Expect a few percent difference.","estimate.save_confirm":"Save","estimate.edit_title":'Edit "{name}"',"estimate.saved":"Saved","estimate.now":"Now","estimate.update_blocked":'"Update to current" needs every side it covers confirmed. Set a reference first.',"estimate.delete":"Delete","estimate.update":"Update to current","estimate.ref_lowering_running":"The bed is lowering past its full travel time. Wait until it has stopped, or press Stop.","editor.configure_dialog":"Configure dialog full card","editor.dialog_configuration":"Dialog full card","editor.dialog_configuration_hint":"These full-card settings apply only inside the dialog. The compact card keeps its own settings.","editor.back_to_compact":"Back to compact configuration","compact.target_fixed":"Controls: {side}","estimate.ref_flat_detail_one":"{motors} is fully down. Sets it to 0%.","action.motor_up":"{motor} up","action.motor_down":"{motor} down","action.motor_stop":"Stop {motor}","card.memory_slot":"Memory {slot}","card.picker_name":"Adjustable Bed Card","card.picker_description":"Control an adjustable bed: position, presets, memory, lighting and massage.","editor.graphic_group":"Bed graphic"};var Bt={"action.on":"P\xE5","action.off":"Av","action.close":"Lukk","action.confirm":"{action}? Dette erstatter den lagrede posisjonen.","editor.open_dialog":"\xC5pne hele kortet i en dialog","editor.show_percentage_graphic":"Vis prosentposisjoner (skjematisk)","editor.show_lumbar_graphic":"Vis en egen korsryggseksjon","editor.show_graphic_labels":"Vis etiketter under grafikken","section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.stop":"Stopp","action.stop_all":"Stopp alt","tap.moving_up":"Beveger seg opp \xB7 trykk for \xE5 stoppe","tap.moving_down":"Beveger seg ned \xB7 trykk for \xE5 stoppe","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus, kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.motors_group":"Motorer","editor.tap_to_move":"Trykk for \xE5 starte og stoppe bevegelse","editor.tap_to_move_hint":"Trykk p\xE5 en pil for \xE5 starte. Trykk p\xE5 en pil eller Stopp for \xE5 avslutte. Bevegelsen stopper av seg selv etter maks 30 sekunder.","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Side","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"Kun oversikt","editor.recipe_quick":"Hurtighandlinger","editor.recipe_controls":"Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Side som styres","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge","section.saved_positions":"Lagrede posisjoner","editor.show_saved_positions":"Lagrede posisjoner","estimate.readout":"\u2248 {percent} %","estimate.readout_was":"Var \u2248 {percent} %","estimate.unknown":"Ukjent","estimate.not_calibrated":"Ikke kalibrert","estimate.chip_estimated":"Ansl\xE5tt","estimate.chip_unconfirmed":"Ubekreftet","estimate.chip_unknown":"Ukjent","estimate.alert_calibrate":"Ansl\xE5tte posisjoner er sl\xE5tt p\xE5, men ikke kalibrert enn\xE5.","estimate.calibrate_now":"Kalibrer n\xE5","estimate.alert_unconfirmed":"Posisjonen er ubekreftet etter omstart. Siste anslag: {values}. Lagrede posisjoner er satt p\xE5 pause til du bekrefter.","estimate.alert_unknown":"Posisjonen er ukjent: {reason}. Lagrede posisjoner er satt p\xE5 pause til du setter referansen.","estimate.reason_not_referenced":"ingen referanse er satt enn\xE5","estimate.reason_restart":"Home Assistant startet p\xE5 nytt","estimate.reason_failed_move":"en bevegelse mislyktes","estimate.reason_untracked_move":"sengen beveget seg uten tidtaking","estimate.reason_hardware_preset":"en forh\xE5ndsinnstilling eller et minne i sengen flyttet den","estimate.reason_remote":"du meldte at fjernkontrollen ble brukt","estimate.reason_connection_lost":"forbindelsen falt ut under en bevegelse","estimate.unchanged":"Den har ikke flyttet seg","estimate.set_reference":"Sett referanse\u2026","estimate.edit":"Rediger","estimate.done":"Ferdig","estimate.edit_hint":"Trykk p\xE5 en posisjon for \xE5 gi den nytt navn, oppdatere eller slette den.","estimate.save":"Lagre\u2026","estimate.footer":"Ansl\xE5tt fra bevegelsestid. Bruk av fjernkontrollen registreres ikke.","estimate.scope_both":"Begge sider","estimate.scope_left":"Bare venstre","estimate.scope_right":"Bare h\xF8yre","estimate.recalled":"Flyttet til {name} (ansl\xE5tt)","estimate.ref_title":"Sett referanse","estimate.ref_text":"Velg hvordan du f\xE5r en kjent posisjon. Sengen flytter seg aldri av seg selv for \xE5 finne den igjen.","estimate.ref_lowering":"Senkingen er ferdig. Sjekk at sengen ligger helt flatt, og bekreft.","estimate.ref_flat":"Sengen er flat n\xE5","estimate.ref_flat_detail":"{motors} er helt nede. Setter dem til 0 %.","estimate.ref_lower":"Senk til flat, s\xE5 bekrefter jeg","estimate.ref_lower_detail":"Senker i hele bevegelsestiden pluss en margin. Du bekrefter etterp\xE5 at den er flat.","estimate.ref_only":"Bare {motor}","estimate.ref_only_detail":"De andre motorene beholder anslaget sitt.","estimate.ref_lower_start":"Senk","estimate.ref_confirm":"Bekreft flat","estimate.save_title":"Lagre n\xE5v\xE6rende posisjon","estimate.name":"Navn","estimate.create_button":"Lag ogs\xE5 en knappeentitet","estimate.create_button_detail":"For automasjoner og tale.","estimate.save_note":"Henting flytter hver motor i den beregnede tiden. Regn med noen prosent avvik.","estimate.save_confirm":"Lagre","estimate.edit_title":"Rediger \xAB{name}\xBB","estimate.saved":"Lagret","estimate.now":"N\xE5","estimate.update_blocked":"\xABOppdater til n\xE5v\xE6rende\xBB krever at alle sidene den dekker er bekreftet. Sett en referanse f\xF8rst.","estimate.delete":"Slett","estimate.update":"Oppdater til n\xE5v\xE6rende","estimate.ref_lowering_running":"Sengen senkes lenger enn hele bevegelsestiden. Vent til den har stoppet, eller trykk Stopp.","editor.configure_dialog":"Konfigurer fullt kort i dialogen","editor.dialog_configuration":"Fullt kort i dialogen","editor.dialog_configuration_hint":"Disse innstillingene gjelder bare det fulle kortet i dialogen. Det kompakte kortet beholder sine egne innstillinger.","editor.back_to_compact":"Tilbake til kompakt konfigurasjon","compact.target_fixed":"Styrer: {side}","estimate.ref_flat_detail_one":"{motors} er helt nede. Setter den til 0 %.","action.motor_up":"{motor} opp","action.motor_down":"{motor} ned","action.motor_stop":"Stopp {motor}","card.memory_slot":"Minne {slot}","card.picker_name":"Adjustable Bed-kort","card.picker_description":"Styr en justerbar seng: posisjon, forh\xE5ndsvalg, minne, lys og massasje.","motor.tv_lift":"TV-heis","editor.graphic_group":"Sengegrafikk"};var V={en:Rt,nb:Bt};function Mi(o){let s=(o||"en").toLowerCase(),e=s.split("-")[0];return V[s]?V[s]:V[e]?V[e]:e==="nn"||e==="no"?V.nb:V.en}function f(o,s,e){return Pe(o?.locale?.language||o?.language,s,e)}function Pe(o,s,e){let i=Mi(o)[s]??V.en[s]??s;if(e)for(let[n,r]of Object.entries(e))i=i.replace(`{${n}}`,r);return i}var qe="adjustable-bed-card";function Pi(){return typeof document<"u"?document.documentElement.lang||navigator.language:void 0}var Ht=o=>({type:qe,name:Pe(o,"card.picker_name"),description:Pe(o,"card.picker_description"),preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(s,e)=>{let t=s.entities[e];return t?.platform!==O||!t.device_id?null:{config:{type:`custom:${qe}`,device_id:t.device_id}}}});function Ai(o,s=Pi()){let e=o.customCards??=[],t=e.findIndex(i=>i.type===qe);t===-1?e.push(Ht(s)):e[t]=Ht(s)}function Ae(o,s,e=window.customElements){e.get(o)||e.define(o,s)}typeof window<"u"&&Ai(window);var Re=globalThis,Be=Re.ShadowRoot&&(Re.ShadyCSS===void 0||Re.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Ye=Symbol(),Dt=new WeakMap,ce=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==Ye)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(Be&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=Dt.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&Dt.set(e,s))}return s}toString(){return this.cssText}},Lt=o=>new ce(typeof o=="string"?o:o+"",void 0,Ye),de=(o,...s)=>{let e=o.length===1?o[0]:s.reduce((t,i,n)=>t+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+o[n+1],o[0]);return new ce(e,o,Ye)},Ot=(o,s)=>{if(Be)o.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=Re.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,o.appendChild(t)}},Xe=Be?o=>o:o=>o instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return Lt(e)})(o):o;var{is:Ri,defineProperty:Bi,getOwnPropertyDescriptor:Hi,getOwnPropertyNames:Di,getOwnPropertySymbols:Li,getPrototypeOf:Oi}=Object,He=globalThis,jt=He.trustedTypes,ji=jt?jt.emptyScript:"",zi=He.reactiveElementPolyfillSupport,pe=(o,s)=>o,he={toAttribute(o,s){switch(s){case Boolean:o=o?ji:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,s){let e=o;switch(s){case Boolean:e=o!==null;break;case Number:e=o===null?null:Number(o);break;case Object:case Array:try{e=JSON.parse(o)}catch{e=null}}return e}},De=(o,s)=>!Ri(o,s),zt={attribute:!0,type:String,converter:he,reflect:!1,useDefault:!1,hasChanged:De};Symbol.metadata??=Symbol("metadata"),He.litPropertyMetadata??=new WeakMap;var z=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=zt){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&Bi(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:n}=Hi(this.prototype,s)??{get(){return this[e]},set(r){this[e]=r}};return{get:i,set(r){let l=i?.call(this);n?.call(this,r),this.requestUpdate(s,l,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??zt}static _$Ei(){if(this.hasOwnProperty(pe("elementProperties")))return;let s=Oi(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(pe("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(pe("properties"))){let e=this.properties,t=[...Di(e),...Li(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(Xe(i))}else s!==void 0&&e.push(Xe(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Ot(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let n=(t.converter?.toAttribute!==void 0?t.converter:he).toAttribute(e,t.type);this._$Em=s,n==null?this.removeAttribute(i):this.setAttribute(i,n),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let n=t.getPropertyOptions(i),r=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:he;this._$Em=i;let l=r.fromAttribute(e,n.type);this[i]=l??this._$Ej?.get(i)??l,this._$Em=null}}requestUpdate(s,e,t,i=!1,n){if(s!==void 0){let r=this.constructor;if(i===!1&&(n=this[s]),t??=r.getPropertyOptions(s),!((t.hasChanged??De)(n,e)||t.useDefault&&t.reflect&&n===this._$Ej?.get(s)&&!this.hasAttribute(r._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:n},r){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,r??e??this[s]),n!==!0||r!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,n]of this._$Ep)this[i]=n;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,n]of t){let{wrapped:r}=n,l=this[i];r!==!0||this._$AL.has(i)||l===void 0||this.C(i,void 0,n,l)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};z.elementStyles=[],z.shadowRootOptions={mode:"open"},z[pe("elementProperties")]=new Map,z[pe("finalized")]=new Map,zi?.({ReactiveElement:z}),(He.reactiveElementVersions??=[]).push("2.1.2");var st=globalThis,Nt=o=>o,Le=st.trustedTypes,Ft=Le?Le.createPolicy("lit-html",{createHTML:o=>o}):void 0,Wt="$lit$",G=`lit$${Math.random().toFixed(9).slice(2)}$`,qt="?"+G,Ni=`<${qt}>`,Y=document,me=()=>Y.createComment(""),ge=o=>o===null||typeof o!="object"&&typeof o!="function",ot=Array.isArray,Fi=o=>ot(o)||typeof o?.[Symbol.iterator]=="function",Je=`[ \t
\f\r]`,ue=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Gt=/-->/g,It=/>/g,W=RegExp(`>|${Je}(?:([^\\s"'>=/]+)(${Je}*=${Je}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),Kt=/'/g,Ut=/"/g,Yt=/^(?:script|style|textarea|title)$/i,nt=o=>(s,...e)=>({_$litType$:o,strings:s,values:e}),d=nt(1),N=nt(2),gs=nt(3),X=Symbol.for("lit-noChange"),c=Symbol.for("lit-nothing"),Vt=new WeakMap,q=Y.createTreeWalker(Y,129);function Xt(o,s){if(!ot(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return Ft!==void 0?Ft.createHTML(s):s}var Gi=(o,s)=>{let e=o.length-1,t=[],i,n=s===2?"<svg>":s===3?"<math>":"",r=ue;for(let l=0;l<e;l++){let a=o[l],p,h,u=-1,m=0;for(;m<a.length&&(r.lastIndex=m,h=r.exec(a),h!==null);)m=r.lastIndex,r===ue?h[1]==="!--"?r=Gt:h[1]!==void 0?r=It:h[2]!==void 0?(Yt.test(h[2])&&(i=RegExp("</"+h[2],"g")),r=W):h[3]!==void 0&&(r=W):r===W?h[0]===">"?(r=i??ue,u=-1):h[1]===void 0?u=-2:(u=r.lastIndex-h[2].length,p=h[1],r=h[3]===void 0?W:h[3]==='"'?Ut:Kt):r===Ut||r===Kt?r=W:r===Gt||r===It?r=ue:(r=W,i=void 0);let y=r===W&&o[l+1].startsWith("/>")?" ":"";n+=r===ue?a+Ni:u>=0?(t.push(p),a.slice(0,u)+Wt+a.slice(u)+G+y):a+G+(u===-2?l:y)}return[Xt(o,n+(o[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},fe=class o{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let n=0,r=0,l=s.length-1,a=this.parts,[p,h]=Gi(s,e);if(this.el=o.createElement(p,t),q.currentNode=this.el.content,e===2||e===3){let u=this.el.content.firstChild;u.replaceWith(...u.childNodes)}for(;(i=q.nextNode())!==null&&a.length<l;){if(i.nodeType===1){if(i.hasAttributes())for(let u of i.getAttributeNames())if(u.endsWith(Wt)){let m=h[r++],y=i.getAttribute(u).split(G),b=/([.?@])?(.*)/.exec(m);a.push({type:1,index:n,name:b[2],strings:y,ctor:b[1]==="."?Qe:b[1]==="?"?et:b[1]==="@"?tt:te}),i.removeAttribute(u)}else u.startsWith(G)&&(a.push({type:6,index:n}),i.removeAttribute(u));if(Yt.test(i.tagName)){let u=i.textContent.split(G),m=u.length-1;if(m>0){i.textContent=Le?Le.emptyScript:"";for(let y=0;y<m;y++)i.append(u[y],me()),q.nextNode(),a.push({type:2,index:++n});i.append(u[m],me())}}}else if(i.nodeType===8)if(i.data===qt)a.push({type:2,index:n});else{let u=-1;for(;(u=i.data.indexOf(G,u+1))!==-1;)a.push({type:7,index:n}),u+=G.length-1}n++}}static createElement(s,e){let t=Y.createElement("template");return t.innerHTML=s,t}};function ee(o,s,e=o,t){if(s===X)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,n=ge(s)?void 0:s._$litDirective$;return i?.constructor!==n&&(i?._$AO?.(!1),n===void 0?i=void 0:(i=new n(o),i._$AT(o,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=ee(o,i._$AS(o,s.values),i,t)),s}var Ze=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??Y).importNode(e,!0);q.currentNode=i;let n=q.nextNode(),r=0,l=0,a=t[0];for(;a!==void 0;){if(r===a.index){let p;a.type===2?p=new _e(n,n.nextSibling,this,s):a.type===1?p=new a.ctor(n,a.name,a.strings,this,s):a.type===6&&(p=new it(n,this,s)),this._$AV.push(p),a=t[++l]}r!==a?.index&&(n=q.nextNode(),r++)}return q.currentNode=Y,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},_e=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=ee(this,s,e),ge(s)?s===c||s==null||s===""?(this._$AH!==c&&this._$AR(),this._$AH=c):s!==this._$AH&&s!==X&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):Fi(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==c&&ge(this._$AH)?this._$AA.nextSibling.data=s:this.T(Y.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=fe.createElement(Xt(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let n=new Ze(i,this),r=n.u(this.options);n.p(e),this.T(r),this._$AH=n}}_$AC(s){let e=Vt.get(s.strings);return e===void 0&&Vt.set(s.strings,e=new fe(s)),e}k(s){ot(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let n of s)i===e.length?e.push(t=new o(this.O(me()),this.O(me()),this,this.options)):t=e[i],t._$AI(n),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=Nt(s).nextSibling;Nt(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},te=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,n){this.type=1,this._$AH=c,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=n,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=c}_$AI(s,e=this,t,i){let n=this.strings,r=!1;if(n===void 0)s=ee(this,s,e,0),r=!ge(s)||s!==this._$AH&&s!==X,r&&(this._$AH=s);else{let l=s,a,p;for(s=n[0],a=0;a<n.length-1;a++)p=ee(this,l[t+a],e,a),p===X&&(p=this._$AH[a]),r||=!ge(p)||p!==this._$AH[a],p===c?s=c:s!==c&&(s+=(p??"")+n[a+1]),this._$AH[a]=p}r&&!i&&this.j(s)}j(s){s===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},Qe=class extends te{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===c?void 0:s}},et=class extends te{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==c)}},tt=class extends te{constructor(s,e,t,i,n){super(s,e,t,i,n),this.type=5}_$AI(s,e=this){if((s=ee(this,s,e,0)??c)===X)return;let t=this._$AH,i=s===c&&t!==c||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,n=s!==c&&(t===c||i);i&&this.element.removeEventListener(this.name,this,t),n&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},it=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){ee(this,s)}};var Ii=st.litHtmlPolyfillSupport;Ii?.(fe,_e),(st.litHtmlVersions??=[]).push("3.3.3");var Jt=(o,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let n=e?.renderBefore??null;t._$litPart$=i=new _e(s.insertBefore(me(),n),n,void 0,e??{})}return i._$AI(o),i};var rt=globalThis,H=class extends z{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=Jt(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return X}};H._$litElement$=!0,H.finalized=!0,rt.litElementHydrateSupport?.({LitElement:H});var Ki=rt.litElementPolyfillSupport;Ki?.({LitElement:H});(rt.litElementVersions??=[]).push("4.2.2");var ve=o=>Math.max(0,Math.min(75,o)),ie=o=>`is-${o.angle===void 0?"unknown":o.feedback??"measured"}`,Zt=o=>o.angle===void 0?"?":o.readout??`${Math.round(o.angle)}\xB0`;function Qt(o){let s=o.middle?122:150,e=o.middle?178:150,t=ve(o.middle?.angle??0)/75*28;return{upperTransform:`rotate(${ve(o.upper.angle??0)} ${s} 70)`,lowerTransform:`rotate(${-ve(o.lower.angle??0)} ${e} 70)`,upperWidth:s-42,lowerX:e,lowerWidth:258-e,middlePath:`M 125 58 C 137 ${58-t} 163 ${58-t} 175 58 L 175 76 C 163 ${76-t} 137 ${76-t} 125 76 Z`}}function at(o,s="theme"){let e=Qt(o),t=e.upperTransform,i=e.lowerTransform,n=(r,l)=>o.stackLabels&&l.label?N`<text x=${r} y="124" text-anchor="middle" class="bed-graphic-label"><tspan
        x=${r}>${l.label}</tspan><tspan x=${r} dy="14">${Zt(l)}</tspan></text>`:N`<text x=${r} y="128" text-anchor="middle" class="bed-graphic-label">${`${l.label?`${l.label} `:""}${Zt(l)}`}</text>`;return N`
    <svg
      class="bed-graphic bed-graphic-${s} ${o.moving?"is-moving":""}"
      viewBox=${o.stackLabels?"0 -44 300 190":"0 -44 300 180"}
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abSingleMattress" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-mattress-stop" offset="0%" stop-opacity="1" />
          <stop class="bed-mattress-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
        <linearGradient id="abSingleFrame" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-frame-stop" offset="0%" stop-opacity="0.88" />
          <stop class="bed-frame-stop" offset="100%" stop-opacity="0.58" />
        </linearGradient>
      </defs>

      <!-- frame + legs -->
      <rect class="bed-frame" x="30" y="78" width="240" height="8" rx="4" fill="url(#abSingleFrame)" />
      <rect class="bed-frame" x="34" y="83" width="6" height="24" rx="3" fill="url(#abSingleFrame)" />
      <rect class="bed-frame" x="260" y="83" width="6" height="24" rx="3" fill="url(#abSingleFrame)" />

      <g class="bed-side-layer" fill="url(#abSingleMattress)">
        <!-- foot panel (right of hinge) -->
        <g class="bed-panel ${ie(o.lower)}" transform=${i}>
          <rect class="bed-surface" x=${e.lowerX} y="58" width=${e.lowerWidth} height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel ${ie(o.upper)}" transform=${t}>
          <rect class="bed-surface" x="42" y="58" width=${e.upperWidth} height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
        ${o.middle?N`<g class="bed-panel bed-lumbar-panel ${ie(o.middle)}">
          <path class="bed-surface" d=${e.middlePath} />
        </g>`:""}
      </g>

      ${o.showLabels!==!1?N`
      ${n(o.middle?80:86,o.upper)}
      ${o.middle?n(150,o.middle):""}
      ${n(o.middle?220:214,o.lower)}
      `:""}
    </svg>
  `}function lt(o){let s=(e,t)=>{let i=Qt(t);return N`
    <g
      class="dual-bed-side dual-bed-side-${e} ${t.moving?"is-moving":""}"
      fill=${`url(#abDual${e==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel ${ie(t.lower)}"
        transform=${i.lowerTransform}
      >
        <rect class="dual-bed-surface" x=${i.lowerX} y="58" width=${i.lowerWidth} height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel ${ie(t.upper)}"
        transform=${i.upperTransform}
      >
        <rect class="dual-bed-surface" x="42" y="58" width=${i.upperWidth} height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
      ${t.middle?N`<g class="dual-bed-panel bed-lumbar-panel ${ie(t.middle)}">
        <path class="dual-bed-surface" d=${i.middlePath} />
      </g>`:""}
    </g>
  `};return N`
    <svg
      class="bed-graphic dual-bed-graphic ${o.left.moving||o.right.moving?"is-moving":""}"
      viewBox="0 -44 300 160"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abDualFrame" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-frame-stop" offset="0%" stop-opacity="0.88" />
          <stop class="bed-frame-stop" offset="100%" stop-opacity="0.58" />
        </linearGradient>
        <linearGradient id="abDualLeft" x1="0" y1="0" x2="0" y2="1">
          <stop class="dual-bed-left-stop" offset="0%" stop-opacity="1" />
          <stop class="dual-bed-left-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
        <linearGradient id="abDualRight" x1="0" y1="0" x2="0" y2="1">
          <stop class="dual-bed-right-stop" offset="0%" stop-opacity="1" />
          <stop class="dual-bed-right-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
      </defs>
      <rect class="dual-bed-frame" x="30" y="78" width="240" height="8" rx="4" fill="url(#abDualFrame)" />
      <rect class="dual-bed-frame" x="34" y="83" width="6" height="24" rx="3" fill="url(#abDualFrame)" />
      <rect class="dual-bed-frame" x="260" y="83" width="6" height="24" rx="3" fill="url(#abDualFrame)" />
      ${s("right",o.right)}
      ${s("left",o.left)}
    </svg>
  `}var ei=o=>typeof o=="number"&&Number.isFinite(o)?o:void 0;function be(o,s){let e=s.estimate,t=e?o?.states[e]:void 0;if(!e||!t)return;let i=t.attributes,n=typeof i.bed_side=="string"?i.bed_side:void 0;if(t.state==="unavailable")return{motor:s.key,entityId:e,state:"not_calibrated",side:n};let r=i.estimate_state,l=r==="tracking"||r==="unconfirmed"||r==="unknown"?r:"unknown",a=Number.parseFloat(t.state);return{motor:s.key,entityId:e,state:l,percent:l==="tracking"&&Number.isFinite(a)?a:ei(i.last_estimate),reason:typeof i.estimate_reason=="string"?i.estimate_reason:void 0,maxAngle:ei(i.max_angle),side:n}}function se(o,s){return s.flatMap(e=>{let t=be(o,e);return t?[t]:[]})}function I(o,s){let e=o.percent===void 0?void 0:`${Math.round(o.percent)}`;return o.state==="tracking"&&e!==void 0?s("estimate.readout",{percent:e}):o.state==="unconfirmed"&&e!==void 0?s("estimate.readout_was",{percent:e}):o.state==="not_calibrated"?s("estimate.not_calibrated"):s("estimate.unknown")}function ct(o){if(o.length!==0)return o.some(s=>s.state==="unknown"||s.state==="not_calibrated")?"unknown":o.some(s=>s.state==="unconfirmed")?"unconfirmed":"estimated"}function ti(o){if(o.some(t=>t.state==="not_calibrated"))return{kind:"calibrate"};let s=o.filter(t=>t.state==="unknown");if(s.length)return{kind:"unknown",reason:s[0].reason};let e=o.filter(t=>t.state==="unconfirmed");if(e.length)return{kind:"unconfirmed",estimates:e}}function ii(o,s){let e=s?o?.states[s]?.attributes.positions:void 0;return Array.isArray(e)?e.flatMap(t=>{if(!t||typeof t!="object")return[];let{id:i,name:n,button:r,beds:l}=t;return typeof i!="string"||typeof n!="string"||!l||typeof l!="object"?[]:[{id:i,name:n,button:r!==!1,beds:l}]}):[]}function si(o,s){return o.filter(e=>{let t=Object.keys(e.beds);return t.length>0&&t.every(i=>s.includes(i))})}function oi(o){let s=Object.keys(o.beds);return s.includes("left")&&s.includes("right")?"both":s.includes("left")?"left":s.includes("right")?"right":"bed"}function ni(o,s){let e=Object.entries(o.beds);return e.length>0&&e.every(([t,i])=>{let n=s[t]??[],r=Object.keys(i);return r.length>0&&r.every(l=>n.find(a=>a.motor===l)?.state==="tracking")})}function Oe(o){return o.length>0&&o.every(s=>s.state==="tracking")}function ri(o){if(!(!o||o.state!=="tracking")&&!(o.percent===void 0||o.maxAngle===void 0))return o.percent/100*o.maxAngle}function ye(o){let s=o.find(i=>i.key==="back"||i.key==="head"),e=o.find(i=>i.key==="legs"||i.key==="feet"),t=o.find(i=>i.key==="lumbar");return s&&e?{upper:s,lower:e,...t?{middle:t}:{}}:void 0}function ai(o,s,e=!1){let t=o.motors.filter(n=>{let r=n.angle??n.position,l=s.states[r??""]?.attributes.unit_of_measurement;return l==="\xB0"||e&&l==="%"}),i=o.motors.filter(n=>{let r=s.states[n.estimate??""];return r!==void 0&&(e||typeof r.attributes.max_angle=="number")});return ye(t)!==void 0||ye(i)!==void 0}function je(o,s=!1){if(!s)return o;let e=ye(o);if(!e?.middle)return o;let t=[e.upper,e.middle,e.lower];return[...t,...o.filter(i=>!t.includes(i))]}function li(o){let s=Math.max(0,Math.min(100,o));return{angle:s*.75,readout:`${Math.round(s)}%`}}function ci(o,s,e=!1){let t=o.angle??o.position,i=s.states[t??""],n=i?.attributes.unit_of_measurement;if(n!=="\xB0"&&n!=="%"||n==="%"&&!e)return;let r=i.state.trim();if(r==="")return;let l=Number(r);if(Number.isFinite(l))return n==="\xB0"?{angle:l}:li(l)}function dt(o,s,e){if(!o)return;if(!s){let n=ri(o);return n===void 0?void 0:{angle:n,readout:`\u2248 ${Math.round(ve(n))}\xB0`,feedback:"estimated"}}let{percent:t,state:i}=o;return t===void 0||i!=="tracking"&&i!=="unconfirmed"?{feedback:"unknown"}:{...li(t),readout:I(o,e),feedback:i==="tracking"?"estimated":"unconfirmed"}}var ze=o=>!!(o.cover||o.up||o.down),pt=o=>o.motors.filter(s=>s.position&&!ze(s)),ht=o=>o.motors.some(ze)||pt(o).length>0||!!o.synchro||!!o.controlSide||!!o.stop,ut=o=>le(o.lights)||!!o.lights.state,mt=o=>o.presets.length+o.presetSaves.length>0,gt=({massage:o})=>o.buttons.length>0||o.numbers.length>0||!!o.selects?.length||!!o.switches?.length||!!o.states?.length||!!o.timer,ft=o=>o.utility.length>0||!!o.utilitySwitches?.length||!!o.utilityNumbers?.length||!!o.utilitySelects?.length||!!o.utilityStates?.length,_t=({climate:o})=>[...o.entities,...o.selects,...o.numbers];function we(o,s,e){return{graphic:ai(o,s,e?.show_percentage_graphic===!0),motors:ht(o),firmness:o.firmness.length>0,presets:mt(o),saved_positions:!!o.savedPositions,memory:o.memory.length>0,lighting:ut(o),massage:gt(o),utility:ft(o),climate:_t(o).length>0,connection:!!(o.connect||o.disconnect)}}var Ui={attribute:!0,type:String,converter:he,reflect:!1,hasChanged:De},Vi=(o=Ui,s,e)=>{let{kind:t,metadata:i}=e,n=globalThis.litPropertyMetadata.get(i);if(n===void 0&&globalThis.litPropertyMetadata.set(i,n=new Map),t==="setter"&&((o=Object.create(o)).wrapped=!0),n.set(e.name,o),t==="accessor"){let{name:r}=e;return{set(l){let a=s.get.call(this);s.set.call(this,l),this.requestUpdate(r,a,o,!0,l)},init(l){return l!==void 0&&this.C(r,void 0,o,l),l}}}if(t==="setter"){let{name:r}=e;return function(l){let a=this[r];s.call(this,l),this.requestUpdate(r,a,o,!0,l)}}throw Error("Unsupported decorator location: "+t)};function oe(o){return(s,e)=>typeof e=="object"?Vi(o,s,e):((t,i,n)=>{let r=i.hasOwnProperty(n);return i.constructor.createProperty(n,t),r?Object.getOwnPropertyDescriptor(i,n):void 0})(o,s,e)}function P(o){return oe({...o,state:!0,attribute:!1})}var pi=["glance","quick","controls"],hi=Object.fromEntries(j.map(o=>[`show_${o}`,!0])),ui={name:"",show_header:!0,animate:!0,show_graphic_labels:!0,show_percentage_graphic:!1,show_lumbar_graphic:!1,...hi,section_order:[],memory_save:!0,memory_slots:[],tap_to_move:!1};function Fe(o){return{...o,show_header:!0,...hi,...o.dialog_config,type:o.type,device_id:o.device_id,layout:"full",open_dialog:!1,navigation_path:void 0,dialog_config:void 0}}function mi(o,s){let e={...o,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:s==="glance"?"names":"angles",show_side_selector:!0,show_motors:s==="controls",show_lighting:!1,show_connection:!1,animate:!0};return s==="glance"?e.compact_actions=[]:delete e.compact_actions,e}function gi(o,s){return[...s.presets,...s.memory.flatMap(e=>e.goto?[e.goto]:[])].flatMap(e=>{let t=o.entities[e]?.translation_key;return t?[{key:t,entityId:e}]:[]})}function di(o,s){let e=o.entities[s],t=o.states[s]?.attributes.bed_side;return Object.values(o.entities).some(i=>i.entity_id!==s&&i.device_id===e?.device_id&&i.translation_key===e?.translation_key&&o.states[i.entity_id]?.attributes.bed_side===t)}function fi(o,s,e){if(!e.includes("."))return[...s].reverse().find(a=>a.key===e);let t=s.find(a=>a.entityId===e);if(t)return t;let i=o.entities[e]?.translation_key,n=s.filter(a=>a.key===i),r=S(o,e),l=n.find(a=>S(o,a.entityId)===r);return l||(n.length===1&&!di(o,e)&&!di(o,n[0].entityId)?n[0]:void 0)}function ne(o,s,e){let t=gi(o,s);if(e){let r=e.flatMap(l=>{let a=fi(o,t,l);return a?[a]:[]});return r.filter((l,a)=>r.findIndex(p=>p.entityId===l.entityId)===a)}let i=t.find(r=>r.key==="preset_flat"),n=t.find(r=>r.key.startsWith("preset_memory_"))??t.find(r=>r!==i);return[i,n].filter(r=>r!==void 0)}function vt(o,s,e,t){let i=[],n=a=>i.find(({action:p,sideOptions:h})=>fi(o,h,a)?.entityId===p.entityId),r=e?[e,...s.filter(a=>a!==e)]:s;for(let a of r){let p=gi(o,a.bed);for(let h of p)n(h.entityId)||i.push({action:h,sideOptions:p})}let l=(t??(e?ne(o,e.bed).map(a=>a.entityId):[])).flatMap(a=>{let p=n(a);return p?[p.action.entityId]:[]});return{options:i.map(({action:a})=>a),selected:[...new Set(l)]}}function Ge(o){return o.stop?[o.stop]:o.motors.flatMap(s=>s.cover?[s.cover]:[])}function Ie(o){if(!(!o||!o.startsWith("/")||/^\/[/\\]/.test(o)||/[\\\s]/.test(o)))return o}function K(o,s){let e=Me(o,s),t=ae(o,e);return e&&t.length?[{key:"both",label:f(o,"card.both_sides"),bed:A(o,e)},...t.map(i=>({key:i,label:L(o,i)??i,bed:A(o,i)}))]:Ce(o,s)?["both","left","right"].map(i=>({key:i,label:f(o,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:A(o,s,i)})):[{key:"both",label:f(o,"card.both_sides"),bed:A(o,s)}]}var _i="5.0.0b8";var Wi="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",qi="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",Yi=(o,s)=>o.length===s.length&&o.every((e,t)=>e===s[t]),J=class extends H{constructor(){super(...arguments);this._editingDialog=!1;this._computeLabel=e=>f(this.hass,`editor.${e.name}`)}get _config(){return this._editingDialog&&this._rootConfig?Fe(this._rootConfig):this._rootConfig}setConfig(e){this._rootConfig=e,(e.layout!=="compact"||!e.open_dialog)&&(this._editingDialog=!1)}_bed(){let e=this._config?.device_id;if(!this.hass||!e)return;let t=K(this.hass,e).map(r=>r.bed),i=t[0];if(!i)return;let n=new Map;for(let r of t)for(let l of r.memory){let a=n.get(l.slot);n.set(l.slot,{slot:l.slot,goto:a?.goto??l.goto,save:a?.save??l.save})}return{...i,memory:[...n.values()].sort((r,l)=>r.slot-l.slot)}}_presentKeys(e){let t=this.hass?K(this.hass,this._config?.device_id).map(i=>i.bed):[e];return j.filter(i=>t.some(n=>we(n,this.hass,this._config)[i]))}_orderedKeys(e){let t=this._presentKeys(e),n=(this._config?.section_order??[]).filter(l=>t.includes(l)),r=t.filter(l=>!n.includes(l));return[...n,...r]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=f(this.hass,"card.memory_slot",{slot:String(e.slot)});return t?S(this.hass,t,i):i}_savedActionIds(e){let t=e.compact_actions;if(!this.hass||!Array.isArray(t)||t.every(a=>typeof a!="string"||a.includes(".")))return t;let i=K(this.hass,e.device_id),n=i.find(a=>a.key===(e.default_target??"both"));if(!t.every(a=>typeof a=="string"))return t;let r=vt(this.hass,i,n,t).selected;if(r.length!==new Set(t).size)return t;let l=a=>ne(this.hass,a.bed,t).map(p=>p.entityId).join()===ne(this.hass,a.bed,r).map(p=>p.entityId).join();return i.every(l)?r:t}_emit(e){if(e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this._editingDialog||(e.compact_actions=this._savedActionIds(e)),e.compact_actions===void 0&&delete e.compact_actions,this._editingDialog&&this._rootConfig){let t=Object.fromEntries(Object.entries(ui).map(([i,n])=>[i,e[i]??n]));e={...this._rootConfig,dialog_config:{...this._rootConfig.dialog_config,...t}}}this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return this._editingDialog?[{name:"name",selector:{text:{}}}]:[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;this._editingDialog||(i.device_id!==t.device_id&&delete i.default_target,i.device_id=t.device_id||void 0),t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let n=this._orderedKeys(e),r=n.indexOf(t),l=r+i;if(r<0||l<0||l>=n.length)return;[n[r],n[l]]=[n[l],n[r]];let a=this._cfg;Yi(n,this._presentKeys(e))?delete a.section_order:a.section_order=n,this._emit(a)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let n=this._memorySlots(e),r=this._config?.memory_slots,l=r&&r.length?r.map(Number):[...n];i?l.includes(t)||l.push(t):l=l.filter(p=>p!==t),l.sort((p,h)=>p-h);let a=this._cfg;l.length===n.length?delete a.memory_slots:a.memory_slots=l,this._emit(a)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?d`
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.sections")}</div>
        ${t.map((i,n)=>{let r=this._config?.[`show_${i}`]!==!1;return d`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${n===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${f(this.hass,"editor.move_up")}
                  aria-label=${f(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Wi}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${n===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${f(this.hass,"editor.move_down")}
                  aria-label=${f(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${qi}></path></svg>
                </button>
              </div>
              <ha-switch
                .checked=${r}
                @change=${l=>this._toggleSection(i,l.target.checked)}
              >${f(this.hass,`editor.show_${i}`)}</ha-switch>
            </div>
          `})}
      </div>
    `:c}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return c;let i=e.memory.some(r=>r.save),n=e.memory.length>1;return!i&&!n?c:d`
      <div class="group">
        <div class="group-title">
          ${f(this.hass,"editor.memory_group")}
        </div>
        ${i?d`<div class="row">
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                >${f(this.hass,"editor.memory_save")}</ha-switch>
              </div>`:c}
        ${n?d`<div class="sub">
                <div class="sub-label">
                  ${f(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(r=>d`
                    <div class="row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${l=>this._toggleSlot(e,r.slot,l.target.checked)}
                      >${this._slotLabel(r)}</ha-checkbox>
                    </div>
                  `)}
              </div>`:c}
      </div>
    `}_tapToMoveToggle(){return d`<div class="row">
        <ha-switch .checked=${this._config?.tap_to_move===!0}
          @change=${e=>this._setOption("tap_to_move",e.target.checked||void 0)}
        >${f(this.hass,"editor.tap_to_move")}</ha-switch>
      </div>
      <p class="hint">${f(this.hass,"editor.tap_to_move_hint")}</p>`}_motorsGroup(e){return this._config?.show_motors===!1||!this._presentKeys(e).includes("motors")?c:d`<div class="group">
      <div class="group-title">${f(this.hass,"editor.motors_group")}</div>
      ${this._tapToMoveToggle()}
    </div>`}_setOption(e,t){this._emit({...this._cfg,[e]:t})}_compactToggle(e,t){return d`<div class="row">
      <ha-switch .checked=${this._config?.[e]??t}
        @change=${i=>this._setOption(e,i.target.checked)}
      >${f(this.hass,e==="show_connection"?"editor.compact_connection":`editor.${e}`)}</ha-switch>
    </div>`}_compactGroup(){let e=this._config,t=K(this.hass,e.device_id),i=t.find(a=>a.key===(e.default_target??"both")),{options:n,selected:r}=vt(this.hass,t,i,e.compact_actions),l=[...r,...n.map(a=>a.entityId).filter(a=>!r.includes(a))];return d`
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        ${this._graphicOptions()}
        <label class="row"><span class="label">${f(this.hass,"editor.compact_labels")}</span>
          <select .value=${e.compact_labels??"angles"}
            @change=${a=>this._setOption("compact_labels",a.target.value)}>
            ${["angles","names","none"].map(a=>d`
              <option value=${a}>${f(this.hass,`editor.labels_${a}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        ${this._compactToggle("open_dialog",!1)}
        ${e.open_dialog?d`<div class="recipes">
          <button @click=${()=>{this._editingDialog=!0}}>
            ${f(this.hass,"editor.configure_dialog")}
          </button>
        </div>`:c}
        <label class="row path-row"><span class="label">${f(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${e.navigation_path??""} placeholder="/dashboard/bed"
            @change=${a=>this._setOption("navigation_path",a.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.compact_controls")}</div>
        ${t.length>1||!i?d`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${f(this.hass,"editor.default_target")}</span>
            <select .value=${e.default_target??"both"}
              @change=${a=>this._setOption("default_target",a.target.value)}>
              ${i?c:d`<option value=${e.default_target}>${f(this.hass,"compact.target_missing")}</option>`}
              ${t.map(a=>d`<option value=${a.key}>${a.label}</option>`)}
            </select>
          </label>`:c}
        ${this._compactToggle("show_motors",!1)}
        ${e.show_motors===!0?this._tapToMoveToggle():c}
        ${this._compactToggle("show_lighting",!1)}
        ${this._compactToggle("show_connection",!1)}
        <p class="hint">${f(this.hass,"editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.compact_actions")}</div>
        <p class="hint">${f(this.hass,"editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${()=>this._setOption("compact_actions",void 0)}>${f(this.hass,"editor.actions_auto")}</button>
          <button @click=${()=>this._setOption("compact_actions",[])}>${f(this.hass,"editor.labels_none")}</button>
        </div>
        ${l.map(a=>{let p=n.find(y=>y.entityId===a),h=r.includes(a),u=r.indexOf(a),m=y=>{let b=[...r];[b[u],b[u+y]]=[b[u+y],b[u]],this._setOption("compact_actions",b)};return d`<div class="row">
            <ha-checkbox .checked=${h} @change=${y=>this._setOption("compact_actions",y.target.checked?[...r,a]:r.filter(b=>b!==a))}
            >${S(this.hass,p.entityId)}</ha-checkbox>
            <button class="icon-btn" ?disabled=${!h||u===0}
              aria-label=${f(this.hass,"editor.move_up")} @click=${()=>m(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!h||u===r.length-1}
              aria-label=${f(this.hass,"editor.move_down")} @click=${()=>m(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return d`<div class="group">
      <label class="row"><span class="label">${f(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${e=>this._setOption("layout",e.target.value)}>
          <option value="full">${f(this.hass,"editor.layout_full")}</option>
          <option value="compact">${f(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${f(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${pi.map(e=>d`
        <button @click=${()=>this._emit({...mi(this._config,e)})}>
          ${f(this.hass,`editor.recipe_${e}`)}
        </button>`)}</div>
    </div>`}_graphicOptions(){let e=this._config;if(!this.hass||e.show_graphic===!1)return c;let t=K(this.hass,e.device_id),i=t.map(p=>p.bed),n=t.length>1?t.filter(p=>p.key!=="both"):t,r=p=>we(p.bed,this.hass,{...e,show_percentage_graphic:!0}).graphic;if(!(e.layout==="compact"?n.every(r):t.some(r)))return c;let a=i.some(p=>p.motors.some(h=>h.key==="lumbar"));return d`
      ${this._compactToggle("show_graphic_labels",!0)}
      ${this._compactToggle("show_percentage_graphic",!1)}
      ${a||e.show_lumbar_graphic?this._compactToggle("show_lumbar_graphic",!1):c}
    `}_graphicGroup(){let e=this._graphicOptions();return e===c?c:d`<div class="group">
      <div class="group-title">${f(this.hass,"editor.graphic_group")}</div>
      ${e}
    </div>`}render(){if(!this.hass||!this._config)return c;let e=this._bed();return d`
      ${this._editingDialog?d`<div class="group">
        <div class="group-title">${f(this.hass,"editor.dialog_configuration")}</div>
        <p class="hint">${f(this.hass,"editor.dialog_configuration_hint")}</p>
        <div class="recipes"><button @click=${()=>{this._editingDialog=!1}}>
          ${f(this.hass,"editor.back_to_compact")}
        </button></div>
      </div>`:c}
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._editingDialog?c:this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():d`
        ${this._graphicGroup()}
        ${e?this._motorsGroup(e):c}
        ${e?this._sectionsGroup(e):c}
        ${e?this._memoryGroup(e):c}
      `}
    `}};J.styles=de`
    select, input { min-width: 0; max-width: 60%; box-sizing: border-box;
      background: var(--card-background-color); color: var(--primary-text-color);
      border: 1px solid var(--divider-color); border-radius: 6px; padding: 8px; font: inherit; }
    .path-row { flex-wrap: wrap; }
    .path-row input { flex: 1; min-width: 180px; max-width: 100%; }
    .recipes { display: flex; gap: 6px; flex-wrap: wrap; }
    .recipes button { background: var(--secondary-background-color); color: var(--primary-text-color);
      border: 1px solid var(--divider-color); border-radius: 7px; min-height: 44px;
      padding: 8px 12px; cursor: pointer; font: inherit; font-size: .85rem; }
    .hint { color: var(--secondary-text-color); font-size: .8rem; line-height: 1.4; }
    button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

    .group {
      margin-top: 16px;
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      padding: 8px 12px 12px;
    }
    .group-title {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--secondary-text-color);
      padding: 4px 0 8px;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 40px;
    }
    .label,
    .row > ha-switch,
    .row > ha-checkbox {
      flex: 1;
      min-width: 0;
      color: var(--primary-text-color);
    }
    .reorder {
      display: inline-flex;
      gap: 2px;
    }
    .icon-btn {
      border: none;
      background: none;
      color: var(--secondary-text-color);
      cursor: pointer;
      width: 28px;
      height: 28px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
    }
    .icon-btn svg {
      width: 20px;
      height: 20px;
      fill: currentColor;
    }
    .icon-btn:hover:not([disabled]) {
      color: var(--primary-color);
      background: var(--secondary-background-color);
    }
    .icon-btn[disabled] {
      opacity: 0.3;
      cursor: default;
    }
    .sub {
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--divider-color);
    }
    .sub-label {
      font-size: 0.8rem;
      color: var(--secondary-text-color);
      padding-bottom: 4px;
    }
  `,T([oe({attribute:!1})],J.prototype,"hass",2),T([P()],J.prototype,"_rootConfig",2),T([P()],J.prototype,"_editingDialog",2);Ae("adjustable-bed-card-editor",J);var Xi=new Set(["back","legs","head","feet"]),M=class extends H{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._tapRevision=0;this._detailsOpen=!1;this._watched=[];this._awaitingState=[];this._compactStopTargets=new Map;this._hold=new Ee({pulse:(e,t)=>Ue(this.hass,e,t),holdControl:(e,t)=>Ve(this.hass,e,t),lease:(e,t,i)=>wt(this.hass,e,t,i),stopCover:(e,t)=>this._stopCompactTarget(e,t??e),stopBed:e=>{e&&this._stopCompactTarget(e)},changed:()=>{this._tapRevision++}});this._focusLossCleanup=null;this._windowPointerEnd=e=>{this._hold.endActiveFromPointer(e.pointerId,e.type==="pointercancel"||e.button===0)};this._windowKeyUp=e=>{(e.key==="Enter"||e.key===" ")&&this._hold.endKeyboard(void 0,void 0,e.key)};this._navigate=()=>{let e=Ie(this._config?.navigation_path);e&&(this._hold.abandon(),history.pushState(null,"",e),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))};this._openDetails=async()=>{if(!this._config?.open_dialog){this._navigate();return}this._hold.abandon(),this._detailsCard||(this._detailsCard=document.createElement(this.localName),this._detailsCard.setConfig(Fe({...this._config,default_target:this._activePairedPane}))),this._detailsCard.hass=this.hass,this._detailsOpen=!0,await this.updateComplete;let e=this.renderRoot.querySelector(".bed-details-dialog");e&&!e.open&&e.showModal()};this._closeDetails=()=>{if(!this._detailsOpen&&!this._detailsCard)return;let e=this.renderRoot.querySelector(".bed-details-dialog");e?.open&&e.close(),this._detailsOpen=!1,this._detailsCard=void 0};this._detailsBackdrop=e=>{if(e.target!==e.currentTarget)return;let t=e.currentTarget.getBoundingClientRect();(e.clientX<t.left||e.clientX>t.right||e.clientY<t.top||e.clientY>t.bottom)&&this._closeDetails()};this._openSettings=()=>{this._hold.abandon(),history.pushState(null,"","/config/integrations/integration/adjustable_bed"),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}}))};this._closeEstimateDialog=()=>{let e=this.renderRoot?.querySelector?.("dialog.estimate-dialog");e?.open&&e.close();let t=this._estimateDialog;t?.kind==="reference"&&t.phase==="lowering"&&this._stopEstimate(t.ctx),this._estimateDialog=void 0}}connectedCallback(){super.connectedCallback(),this._removeHoldLifecycle=St(this._hold,document,window),window.addEventListener("pointerup",this._windowPointerEnd),window.addEventListener("pointercancel",this._windowPointerEnd),window.addEventListener("keyup",this._windowKeyUp),this._focusLossCleanup=kt(window,document,()=>document.visibilityState==="hidden",()=>this._hold.releaseOnFocusLoss())}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===O)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._detailsOpen&&this._closeDetails(),this._config&&(this._compactStopTargets.size>0?this._stopCompact():this._hold.abandon()),(e.device_id!==this._config?.device_id||e.default_target!==this._config?.default_target)&&(this._activePairedPane=e.default_target??"both"),this._config=e}getCardSize(){if(this._config?.layout!=="compact")return this._fullCardSize();let e=this._config;return Math.ceil((24+(e.show_header!==!1?36:0)+(e.show_graphic!==!1?150:0)+(e.compact_labels!=="none"?40:0)+(e.compact_actions?.length===0?0:110)+(e.show_motors===!0?180:0)+(e.show_lighting===!0?70:0)+(e.show_connection===!0?50:0))/50)}_fullCardSize(){let e=this._config,t=this.hass;if(!e||!t)return 8;let i=K(t,e.device_id).map(r=>r.bed),n=r=>j.filter(l=>e[`show_${l}`]!==!1&&we(r,t,e)[l]).reduce((l,a)=>l+(a==="graphic"?3:a==="motors"?1+r.motors.length:2),0);return(i.length>1?2:1)+Math.max(0,...i.map(n))}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){window.removeEventListener("pointerup",this._windowPointerEnd),window.removeEventListener("pointercancel",this._windowPointerEnd),window.removeEventListener("keyup",this._windowKeyUp),this._focusLossCleanup?.(),this._focusLossCleanup=null,this._removeHoldLifecycle?.(),this._removeHoldLifecycle=void 0,super.disconnectedCallback(),this._hold.abandon(),this._closeEstimateDialog(),this._closeDetails()}shouldUpdate(e){if(e.has("_config")||e.has("_detailsOpen")||e.has("_saveModeFor")||e.has("_activePairedPane")||e.has("_synchronizingTo")||e.has("_synchronizationFailed")||e.has("_estimateDialog")||e.has("_savedEditFor")||e.has("_tapRevision")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices||t.formatEntityName!==this.hass.formatEntityName)return!0;for(let i of[...this._watched,...this._awaitingState])if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return c;if(!this._config.device_id)return this._notice("card.no_device");let e=this.hass.states;this._awaitingState=Object.values(this.hass.entities).filter(a=>a.platform===O&&!e[a.entity_id]).map(a=>a.entity_id);let t=Me(this.hass,this._config.device_id),i=ae(this.hass,t);if(t&&i.length)return this._renderPaired(t,i);if(this._config.device_id&&Ce(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let n=A(this.hass,this._config.device_id);if(this._watched=this._collectWatched(n),F(n))return this._notice("card.no_entities");if(this._config.layout==="compact")return this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:n}],!1);let r=this._config.device_id,l={deviceId:r,paired:!1,sides:[{key:"bed",deviceId:r,label:this._title(),motors:n.motors}],savedPositions:n.savedPositions};return d`
      <ha-card>
        ${this._header(n)}
        ${this._renderSections(n,"theme",void 0,void 0,void 0,l)}
        ${this._estimateDialogTemplate()}
      </ha-card>
    `}_renderSections(e,t="theme",i,n,r,l){let a=this._config,p={graphic:()=>a.show_graphic!==!1?i??this._graphic(e,t):c,motors:()=>a.show_motors!==!1?this._motors(e,n,r,l):c,firmness:()=>a.show_firmness!==!1?this._firmness(e):c,presets:()=>a.show_presets!==!1?this._presets(e):c,saved_positions:()=>a.show_saved_positions!==!1&&l?this._savedPositions(l):c,memory:()=>a.show_memory!==!1?this._memory(e):c,lighting:()=>a.show_lighting!==!1?this._lighting(e):c,massage:()=>a.show_massage!==!1?this._massage(e):c,utility:()=>a.show_utility!==!1?this._utility(e):c,climate:()=>a.show_climate!==!1?this._climate(e):c,connection:()=>a.show_connection!==!1?this._connection(e):c};return this._orderedSections().map(h=>p[h]?.()??c)}_renderPaired(e,t){let i=this.hass,n=A(i,e),r=t.map((m,y)=>({key:m,label:L(i,m)??m,shortLabel:Tt(L(i,m)??m,L(i,e)),bed:A(i,m),graphicTone:y===0?"left":"right",synchronizationTarget:{deviceId:m}})),l=r.flatMap(m=>m.bed.stop?[m.bed.stop]:[]),a=n.stop,p=[...new Set([...a?[a]:[],...l])],h=r.map((m,y)=>({key:this._estimateSideKey(m.bed,y),deviceId:m.key,label:m.label,motors:m.bed.motors})),u=[{key:"both",label:f(i,"card.both_sides"),bed:n,stopScope:p,remainingStopIds:l,estimate:{deviceId:e,side:"both",paired:!0,sides:h,savedPositions:n.savedPositions}},...r.map((m,y)=>({...m,stopScope:m.bed.stop?[m.bed.stop]:[],estimate:{deviceId:m.key,paired:!0,sides:[h[y]],savedPositions:n.savedPositions}}))];return this._watched=[n,...r.map(m=>m.bed)].flatMap(m=>this._collectWatched(m)),F(n)&&r.every(m=>F(m.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,u)}_renderSingleAddressPaired(e){let t=this.hass,i={both:A(t,e,"both"),left:A(t,e,"left"),right:A(t,e,"right")},n=[i.left.stop,i.right.stop].filter(r=>r!==void 0);return this._watched=Object.values(i).flatMap(r=>this._collectWatched(r)),Object.values(i).every(r=>F(r))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:f(t,"card.both_sides"),bed:i.both,stopScope:[...new Set([i.both.stop,...n].filter(r=>r!==void 0))],remainingStopIds:n},{key:"left",label:f(t,"card.left_side"),bed:i.left,graphicTone:"left",stopScope:i.left.stop?[i.left.stop]:[],synchronizationTarget:{deviceId:e,side:"left"}},{key:"right",label:f(t,"card.right_side"),bed:i.right,graphicTone:"right",stopScope:i.right.stop?[i.right.stop]:[],synchronizationTarget:{deviceId:e,side:"right"}}])}_renderPairedCard(e,t){if(this._config?.layout==="compact")return this._renderCompact(e,t,!0);let i=t.filter(a=>!F(a.bed)),n=i.find(a=>a.key===this._activePairedPane)??i[0],r=i.filter(a=>a.key!=="both"),l=n.key==="both";return d`
      <ha-card class="paired-card">
        ${this._header(n.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
          @keydown=${a=>this._paneTabKey(a,i,n.key)}
        >
          ${i.map((a,p)=>d`
              <button
                class="pane-tab side-${a.graphicTone??"theme"} ${a.key===n.key?"active":""}"
                role="tab"
                id=${`pane-tab-${p}`}
                aria-controls="pane-panel"
                aria-selected=${a.key===n.key?"true":"false"}
                aria-label=${a.label}
                tabindex=${a.key===n.key?"0":"-1"}
                @click=${()=>this._selectPairedPane(a.key)}
              >
                ${a.graphicTone?d`<span class="dual-swatch" aria-hidden="true"></span>`:c}
                <span>${this._paneTabLabel(a)}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" id="pane-panel"
          aria-labelledby=${`pane-tab-${i.indexOf(n)}`}>
          ${this._renderSections(n.bed,n.graphicTone,l?this._pairedOverview(r):void 0,n.stopScope,n.remainingStopIds,n.estimate)}
          ${l&&this._config?.show_lighting!==!1?this._combinedLighting(n.bed,r):c}
          ${l&&this._config?.show_connection!==!1?this._combinedBluetooth(r):c}
        </div>
        ${this._estimateDialogTemplate()}
      </ha-card>
    `}_paneTabLabel(e){return e.key==="both"?f(this.hass,"card.both"):e.shortLabel??e.label}_paneTabKey(e,t,i){let n=t.findIndex(p=>p.key===i),r=getComputedStyle(this).direction==="rtl",l={ArrowRight:r?-1:1,ArrowLeft:r?1:-1}[e.key],a=l!==void 0?(n+l+t.length)%t.length:e.key==="Home"?0:e.key==="End"?t.length-1:void 0;a!==void 0&&(e.preventDefault(),this._selectPairedPane(t[a].key),this.updateComplete.then(()=>this.renderRoot.querySelector(`#pane-tab-${a}`)?.focus()))}_renderCompact(e,t,i){let n=this._config,r=t.find(_=>_.key===this._activePairedPane),l=r?.bed,a=l?ne(this.hass,l,n.compact_actions):[],p=n.show_motors===!0&&l?l.motors.filter(_=>_.cover||_.up||_.down||_.position):[],h=a.length>0||p.length>0||n.show_lighting===!0,u=n.compact_actions?.length!==0||n.show_motors===!0||n.show_lighting===!0,m=i?t.filter(_=>_.key!=="both"):t,y=!!l&&Ge(l).length>0,b=a.length>0||p.length>0,E=n.open_dialog||Ie(n.navigation_path);return d`
      <ha-card class="compact-card ${u?"":"compact-glance"} ${n.animate===!1?"no-animation":""}">
        ${n.show_header!==!1?d`
          <div class="compact-header">
            <span class="title">${this._title(e)}</span>
            ${E?d`<button class="compact-open" @click=${this._openDetails}
              aria-label=${f(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:c}
          </div>`:c}
        ${i&&u?n.show_side_selector!==!1?d`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${t.filter(_=>!F(_.bed)).length}`}
            aria-label=${f(this.hass,"compact.target")}>
            ${t.filter(_=>!F(_.bed)).map(_=>d`
              <button class="pane-tab side-${_.graphicTone??"theme"} ${_.key===r?.key?"active":""}"
                aria-pressed=${_.key===r?.key?"true":"false"}
                aria-label=${_.label}
                title=${_.label}
                @click=${()=>this._selectPairedPane(_.key)}>
                ${_.graphicTone?d`<span class="dual-swatch" aria-hidden="true"></span>`:c}
                <span class="compact-tab-label">${this._paneTabLabel(_)}</span>
              </button>`)}
          </div>`:d`<div class="compact-target">
            ${r?f(this.hass,"compact.target_fixed",{side:r.label}):f(this.hass,"compact.target_missing")}
          </div>`:c}
        ${n.show_graphic!==!1?this._compactGraphic(m):c}
        ${this._compactReadouts(m)}
        ${!r&&u?d`<div class="hint" role="status">
          ${f(this.hass,"compact.target_missing")}</div>`:c}
        ${p.length?d`<div class="rows compact-motors">
          ${p.map(_=>_.cover||_.up||_.down?this._motorRow(_,l?.stop,!0,r?.stopScope,r?.remainingStopIds):this._moreInfoRow(_.position))}
        </div>`:c}
        ${a.length||b||this._compactStopTargets.size?d`
          <div class="tiles compact-actions">
            ${a.map(({entityId:_})=>d`<button class="tile"
              ?disabled=${!y||!this._available(_)}
              @click=${()=>this._compactRecall(_,l)}>
              ${this._icon(_)}<span class="tile-label">${S(this.hass,_)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!y&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(l)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${f(this.hass,"action.stop")}</span>
            </button>
          </div>`:c}
        ${n.show_lighting===!0&&l?d`
          ${this._lighting(l)}
          ${i&&r?.key==="both"?this._combinedLighting(l,m):c}
        `:c}
        ${n.show_connection===!0?i&&r?.key==="both"?this._combinedBluetooth(m):d`<div class="compact-connections">
          ${m.map(_=>{let x=this._connectionStatus(_.bed);return x?d`<span>${this._connectionDot(_.bed)}
              ${_.label}: ${f(this.hass,`status.${x}`)}</span>`:c})}
        </div>`:c}
        ${!h&&n.show_graphic===!1&&n.compact_labels==="none"&&n.show_header===!1&&n.show_connection!==!0?d`<div class="hint">${this._title(e)}</div>`:c}
        ${this._estimateDialogTemplate()}
      </ha-card>
      ${this._detailsOpen?d`<dialog class="bed-details-dialog" aria-label=${this._title(e)}
        @close=${this._closeDetails} @click=${this._detailsBackdrop}>
        <div class="bed-details-heading">
          <strong>${this._title(e)}</strong>
          <button class="bed-details-close" @click=${this._closeDetails}
            aria-label=${f(this.hass,"action.close")}>✕</button>
        </div>
        <div class="bed-details-content">${this._detailsCard}</div>
      </dialog>`:c}`}_compactGraphic(e){let t=e.map(u=>this._graphicState(u.bed)),i=t[0],n=t[1],r=t.length>0&&t.every(u=>u!==void 0),l=e.map((u,m)=>`${u.label}: ${t[m]?this._positionSummary(t[m]):f(this.hass,"compact.no_position")}`).join(". "),a=r&&i?n?lt({left:i,right:n}):at({...i,upper:{...i.upper,label:i.middle?i.upper.label:void 0},lower:{...i.lower,label:i.middle?i.lower.label:void 0}}):d`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${f(this.hass,"compact.no_position")}</span></div>`,p=this._config?.show_percentage_graphic===!0&&r&&t.some(u=>u?.estimated)?ct(e.flatMap(u=>se(this.hass,u.bed.motors))):void 0,h=d`${a}${p?d`<span class="estimate-chip chip-${p}
      compact-estimate-chip">${this._t(`estimate.chip_${p}`)}</span>`:c}`;return this._config?.open_dialog||Ie(this._config?.navigation_path)?d`<button class="compact-graphic" @click=${this._openDetails}
          aria-label="${f(this.hass,"compact.open")}. ${l}">${h}</button>`:d`<div class="compact-graphic" role="img" aria-label=${l}>${h}</div>`}_compactReadouts(e){let t=this._config?.compact_labels??"angles";return t==="none"?c:d`<div class="compact-readouts ${t==="names"?"compact-names":""}">
      ${e.map(i=>d`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span class="compact-side-label" aria-hidden="true">${i.shortLabel??i.label}</span>
          <span class="visually-hidden">${i.label}</span>
        </span>
        ${t==="angles"?d`<span class="compact-position"
          title=${je(i.bed.motors,this._config?.show_lumbar_graphic===!0).map(n=>`${this._motorName(n)} ${this._compactReadout(n)??"?"}`).join(" \xB7 ")}
        >${je(i.bed.motors,this._config?.show_lumbar_graphic===!0).filter(n=>n.angle||n.position||n.cover||n.estimate).map(n=>this._compactReadout(n)??"?").join(" / ")||f(this.hass,"compact.no_position")}</span>`:c}
      </div>`)}
    </div>`}_compactReadout(e){return e.angle||e.position||!e.estimate?this._readout(e):dt(be(this.hass,e),!0,(t,i)=>this._t(t,i))?.readout??"?"}_available(e){let t=this._state(e)?.state;return t!==void 0&&t!=="unavailable"}_compactRecall(e,t){this._hold.abandon(),Ge(t).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(e),this.requestUpdate()}_stopCompact(e){let t=[...new Set([...e?Ge(e):[],...this._compactStopTargets.keys()])];this._hold.cancelForStopScope(t);for(let i of t)this._compactStopTargets.has(i)||this._compactStopTargets.set(i,Symbol());for(let i of this._compactStopTargets.keys())this._stopCompactTarget(i);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(e,t=e){let i=this._compactStopTargets.get(t),n=e.startsWith("cover.");this.hass?.callService(n?"cover":"button",n?"stop_cover":"press",{entity_id:e}).then(()=>{i!==void 0&&this._compactStopTargets.get(t)===i&&(this._compactStopTargets.delete(t),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(e){this._activePairedPane!==e&&(this._hold.endTap(),this._activePairedPane=e,this._saveModeFor=void 0,this._savedEditFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(e){if(!e.connectivity)return;let t=this._state(e.connectivity);return t?.attributes?.state_detail==="connecting"?"connecting":t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(e){let t=this._connectionStatus(e);return t?d`<span
      class="connection-dot ${t}"
      title=${f(this.hass,`status.${t}`)}
    ></span>`:c}_pairedOverview(e){let t=e.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(t.length<2)return c;let[i,n]=t;return d`
      <div class="graphic dual-graphic">
        ${lt({left:i.graphic,right:n.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,n].map(({pane:r,graphic:l},a)=>d`
            <div class="dual-readout side-${a===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${r.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(l)}
              </span>
            </div>
          `)}
      </div>
      ${this._synchronizeSelector(i.pane,n.pane)}
    `}_synchronizeSelector(e,t){if(!e.synchronizationTarget||!t.synchronizationTarget)return c;let i=this._synchronizationPlan(e.bed,t.bed),n=this._synchronizationPlan(t.bed,e.bed);if(i.length===0&&n.length===0)return c;let r=this._synchronizingTo!==void 0;return d`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${f(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${f(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"left")}
          >
            ${this._synchronizingTo==="left"?d`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:d`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${f(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||n.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"right")}
          >
            ${this._synchronizingTo==="right"?d`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:d`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?d`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${f(this.hass,"sync.incomplete")}</span>
          </div>`:c}
    `}_synchronizationPlan(e,t){let i=new Map(t.motors.map(l=>[l.key,l])),n=e.motors.filter(l=>Xi.has(l.key)&&i.has(l.key)&&this._hasPositionFeedback(l)&&this._hasPositionFeedback(i.get(l.key)));if(n.length===0)return[];let r=n.map(l=>({motor:l.key,position:this._angle(l)}));return r.some(l=>l.position===void 0)||n.some(l=>this._angle(i.get(l.key))===void 0)?[]:r}_hasPositionFeedback(e){return e.angle!==void 0||e.position!==void 0}async _synchronizePositions(e,t,i){if(this._synchronizingTo||!this.hass)return;let n=i==="left"?e:t,r=i==="left"?t:e,l=r.synchronizationTarget;if(!l)return;let a=this._synchronizationPlan(n.bed,r.bed);if(a.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(O,"set_positions",{device_id:[l.deviceId],positions:a,...l.side?{side:l.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(e){return(e.upperMotor===e.lowerMotor?[e.upperMotor]:[e.upperMotor,...e.middleMotor?[e.middleMotor]:[],e.lowerMotor]).map(i=>{let n=this._readout(i);return n?`${this._motorName(i)} ${n}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(e,t){if(this._hasLighting(e))return c;let i=t.map(u=>this._mainLight(u.bed)).filter(u=>u!==void 0);if(i.length===0)return c;let n=i.filter(u=>this._state(u)?.state==="on").length,r=n===i.length,l=n>0,a=r?"combined.on":l?"combined.mixed":"combined.off",p=f(this.hass,"combined.lights");if(i.some(u=>{let m=this._state(u);return m?.attributes.assumed_state===!0||m?.state!=="on"&&m?.state!=="off"})){let u=this._t("action.off"),m=this._t("action.on");return d`
        ${this._heading("section.lighting")}
        <div class="entity-row combined-entity-row" role="group" aria-label=${p}>
          <ha-icon class="icon" icon="mdi:lightbulb-group-outline"></ha-icon>
          <div class="entity-row-text">
            <span>${p}</span>
          </div>
          <button class="dialog-btn" aria-label=${`${p}: ${u}`}
            @click=${()=>this._setEntities(i,!1)}>${u}</button>
          <button class="dialog-btn" aria-label=${`${p}: ${m}`}
            @click=${()=>this._setEntities(i,!0)}>${m}</button>
        </div>
      `}return d`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${l?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${p}</span>
          <span class="secondary">${f(this.hass,a)}</span>
        </div>
        <button
          class="toggle ${l?"on":""} ${l&&!r?"mixed":""}"
          role="switch"
          aria-label=${p}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(e){let t=e.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return t.length===0?c:d`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${t.map(({pane:i,entityId:n})=>{let r=this._connectionStatus(i.bed),a=this._state(n)?.attributes.rssi;return d`
            <div class="bluetooth-receiver" role="group" aria-label=${i.label}>
            <button
              class="bluetooth-status ${r}"
              @click=${()=>this._moreInfo(n)}
            >
              <ha-icon
                icon=${r==="connected"?"mdi:bluetooth-connect":r==="connecting"?"mdi:bluetooth-transfer":r==="idle"?"mdi:bluetooth":"mdi:bluetooth-off"}
              ></ha-icon>
              <span class="bluetooth-copy">
                <span>${i.label}</span>
                <span class="bluetooth-detail">
                  ${f(this.hass,`status.${r}`)}${typeof a=="number"?` \xB7 ${a} dBm`:""}
                </span>
              </span>
            </button>
            <div class="tiles">
              ${i.bed.connect?this._tile(i.bed.connect,()=>this._press(i.bed.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):c}
              ${i.bed.disconnect?this._tile(i.bed.disconnect,()=>this._press(i.bed.disconnect),{icon:"mdi:bluetooth-off"}):c}
            </div>
            </div>
          `})}
      </div>
    `}_mainLight(e){return e.lights.light??e.lights.switch}_hasLighting(e){return le(e.lights)}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...j];let t=new Set(j),i=e.filter(r=>t.has(r)),n=j.filter(r=>!i.includes(r));return[...i,...n]}_header(e,t){let i=this._connectionStatus(e),n={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return d`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${i===void 0?c:d`
                <button
                  class="conn ${n[i].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${f(this.hass,n[i].key)}
                  aria-label=${f(this.hass,n[i].key)}
                >
                  <ha-icon icon=${n[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e,t="theme"){let i=this._graphicState(e);return i?d`
      <div class="graphic">
        ${at(i,t)}
      </div>
    `:c}_graphicState(e){let t=this.hass;if(!t)return;let i=this._config?.show_percentage_graphic===!0,n=e.motors.filter(_=>{let x=_.angle??_.position,C=this._state(x??"")?.attributes.unit_of_measurement;return C==="\xB0"||i&&C==="%"}),r=n.length===0,l=_=>r?dt(be(t,_),i,(x,C)=>this._t(x,C)):ci(_,t,i),a=ye(r?e.motors.filter(_=>l(_)!==void 0):n);if(!a)return;let{upper:p,lower:h}=a,u=this._config?.show_lumbar_graphic===!0,m=u?e.motors.find(_=>_.key==="lumbar"):void 0,y=l(p),b=l(h);if(!y||!b)return;let E=!r&&e.motors.some(_=>{let x=_.cover?this._state(_.cover)?.state:void 0;return x==="opening"||x==="closing"});return{upperMotor:p,showLabels:this._config?.show_graphic_labels!==!1,stackLabels:i||u,lowerMotor:h,middleMotor:m,upper:{label:this._motorName(p),...y},lower:{label:this._motorName(h),...b},middle:m?{label:this._motorName(m),...l(m)}:void 0,moving:E,...r?{estimated:!0}:{}}}_motors(e,t,i,n){let r=t??(e.stop?[e.stop]:[]);if(!ht(e))return c;let l=je(e.motors,this._config?.show_lumbar_graphic===!0).filter(ze),a=pt(e),p=l.length>0||a.length>0||!!e.synchro||!!e.controlSide,h=n?this._contextEstimates(n):[];return d`
      ${n&&h.length?this._estimateAlertTemplate(n,h):c}
      ${p?this._positionHeading(h):c}
      ${n?.side==="both"?this._estimateOverview(n):c}
      ${e.controlSide?this._moreInfoRow(e.controlSide):c}
      ${e.synchro?this._toggleRow(e.synchro):c}
      ${l.length?d`<div class="rows">
              ${l.map(u=>this._motorRow(u,e.stop,!1,r,i))}
            </div>`:c}
      ${a.length?d`<div class="rows">
              ${a.map(u=>this._moreInfoRow(u.position))}
            </div>`:c}
      ${e.stop?d`<button class="stop-all" @click=${()=>Te(this._hold,e.stop,r,void 0,this.hass)} ?data-armed=${this._hold.tapMoving}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${f(this.hass,"action.stop_all")}</span>
            </button>`:c}
    `}_firmness(e){return e.firmness.length===0?c:d`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t,i=!1,n,r){let l=this._hold.tapDirection(e),a=l?f(this.hass,`tap.moving_${l}`):this._readout(e),p=e.position??e.estimate,h=!!e.cover||!!t,u=d`
      <span>${this._motorName(e)}</span>
      ${a&&!i?d`<span class="readout ${l?"moving":""}">${a}</span>`:c}
    `;return d`
      <div class="row">
        ${p?d`<button
              class="row-label position-label"
              aria-label=${S(this.hass,p)}
              @click=${()=>this._moreInfo(p)}
            >${u}</button>`:d`<div class="row-label">${u}</div>`}
        <div class="control-group">
          ${i?this._motorDirection(e,"down",t,n,r):c}
          ${this._motorDirection(e,"up",t,n,r)}
          ${i?c:d`<button
            class="cg-btn"
            aria-label=${f(this.hass,"action.motor_stop",{motor:this._motorName(e)})}
            @click=${()=>this._motorStop(e,t,n)}
            ?disabled=${!h}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?c:this._motorDirection(e,"down",t,n,r)}
        </div>
      </div>
    `}_motorDirection(e,t,i,n,r){let l=e.cover??e[t],a=!!e.cover||!!i,p=!l||this._config?.layout==="compact"&&(!a||!this._available(l));if(this._config?.tap_to_move===!0&&yt(e,t)){let h=this._hold.tapDirection(e)===t;return d`
        <button class="cg-btn tap ${h?"moving":""}"
          aria-label=${f(this.hass,`action.motor_${t}`,{motor:this._motorName(e)})}
          aria-pressed=${h?"true":"false"}
          @keydown=${u=>{u.repeat&&(u.key==="Enter"||u.key===" ")&&u.preventDefault()}}
          @click=${()=>this._tapMove(e,t,i,n,r)}
          ?disabled=${p&&!h}
        ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`}return d`
      <button class="cg-btn"
        aria-label=${f(this.hass,`action.motor_${t}`,{motor:this._motorName(e)})}
        @pointerdown=${h=>this._startHold(h,e,t,i,n,r)}
        @pointerup=${h=>this._endPointerHold(h,e,i)}
        @pointercancel=${h=>this._endPointerHold(h,e,i)}
        @keydown=${h=>this._startHold(h,e,t,i,n,r)}
        @keyup=${h=>this._endKeyHold(h,e,i)}
        @blur=${()=>this._hold.endKeyboard(e,i)}
        @click=${h=>this._activateWithoutPointer(h,e,t,i,n)}
        ?disabled=${p}
      ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`}_presets(e){return mt(e)?d`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._actionTile(t,e.stop))}
        ${e.presetSaves.map(t=>this._actionTile(t))}
      </div>
    `:c}_utility(e){return ft(e)?d`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${e.utility.map(t=>this._actionTile(t,e.stop))}
      </div>
      ${e.utilitySwitches?.map(t=>this._switchRow(t))}
      ${e.utilitySelects?.map(t=>this._moreInfoRow(t))}
      ${e.utilityNumbers?.map(t=>this._moreInfoRow(t))}
      ${e.utilityStates?.map(t=>this._moreInfoRow(t))}
    `:c}_actionTile(e,t,i=()=>this._press(e)){let n=$t(this.hass,e);return n?this._heldActionTile(e,n,t):this._tile(e,i)}_heldActionTile(e,t,i){return d`<button class="tile"
      aria-label=${S(this.hass,e)}
      @pointerdown=${n=>this._startHold(n,t,"up",i)}
      @pointerup=${n=>this._endPointerHold(n,t,i)}
      @pointercancel=${n=>this._endPointerHold(n,t,i)}
      @keydown=${n=>this._startHold(n,t,"up",i)}
      @keyup=${n=>this._endKeyHold(n,t,i)}
      @blur=${()=>this._endHold(t,i)}
      @click=${n=>this._activateWithoutPointer(n,t,"up",i)}
      ?disabled=${!i||!this._available(e)}>
      ${this._icon(e)}
      <span class="tile-label">${S(this.hass,e)}</span>
    </button>`}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let a=new Set(i.map(Number));t=t.filter(p=>a.has(p.slot))}if(t.length===0)return c;let n=this._config?.memory_save!==!1&&t.some(a=>a.save),r=t.map(a=>a.save??a.goto??String(a.slot)).join("|"),l=this._saveModeFor===r;return d`
      <div class="section-heading heading-row">
        <span>${f(this.hass,"section.memory")}</span>
        ${n?d`<button
                class="set-btn ${l?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${l?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${f(this.hass,l?"memory.cancel":"memory.set")}</span>
              </button>`:c}
      </div>
      ${l?d`<div class="hint">${f(this.hass,"memory.set_hint")}</div>`:c}
      <div class="tiles">${t.map(a=>this._memoryTile(a,l,e.stop))}</div>
    `}_memoryTile(e,t,i){let n=e.goto??e.save;if(t){let l=!!e.save;return d`
        <button
          class="tile ${l?"save-mode":"is-disabled"}"
          ?disabled=${!l}
          @click=${()=>l&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${S(this.hass,n)}</span>
        </button>
      `}let r=!!e.goto;return r?this._actionTile(e.goto,i):d`
      <button
        class="tile ${r?"":"is-disabled"}"
        ?disabled=${!r}
        @click=${()=>e.goto&&this._press(e.goto)}
      >
        ${this._icon(n)}
        <span class="tile-label">${S(this.hass,n)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;if(!ut(e))return c;let n=i||t.state||t.level||t.numbers?.length||t.timer||t.toggle||t.cycle||t.timerMinutes||t.timerToggle||t.buttons?.length;return d`
      ${this._heading("section.lighting")}
      ${t.mood&&n?this._subheading("lighting.floor"):c}
      ${i?i===t.switch?this._switchRow(i):this._toggleRow(i):c}
      ${t.switches?.map(r=>this._switchRow(r))}
      ${t.state?this._moreInfoRow(t.state):c}
      ${t.states?.map(r=>this._moreInfoRow(r))}
      ${t.level?this._moreInfoRow(t.level):c}
      ${t.numbers?.map(r=>this._moreInfoRow(r))}
      ${t.timer?this._moreInfoRow(t.timer):c}
      ${t.timerMinutes?this._moreInfoRow(t.timerMinutes):c}
      ${!t.timerAppliesImmediately&&(t.timerMinutes||t.timerToggle)?d`<div class="hint">${f(this.hass,"lighting.timer_pending")}</div>`:c}
      ${t.toggle||t.cycle||t.timerToggle||t.buttons?.length?d`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):c}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):c}
              ${t.timerToggle?this._tile(t.timerToggle,()=>this._press(t.timerToggle)):c}
              ${t.buttons?.map(r=>this._actionTile(r,e.stop))}
            </div>`:c}
      ${t.mood?d`
        ${this._subheading("lighting.mood")}
        ${t.mood.selects.map(r=>this._moreInfoRow(r))}
        ${t.mood.numbers.map(r=>this._moreInfoRow(r))}
        ${t.mood.toggle||t.mood.buttons?.length?d`<div class="tiles">
          ${t.mood.toggle?this._tile(t.mood.toggle,()=>this._press(t.mood.toggle)):c}
          ${t.mood.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
        </div>`:c}
      `:c}
    `}_massage(e){let t=e.massage;return gt(e)?d`
      ${this._heading("section.massage")}
      ${t.buttons.length?d`<div class="tiles">
              ${t.buttons.map(i=>this._actionTile(i,e.stop))}
            </div>`:c}
      ${t.switches?.map(i=>this._switchRow(i))}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.selects?.map(i=>this._moreInfoRow(i))}
      ${t.states?.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):c}
    `:c}_climate(e){let t=_t(e);return t.length===0?c:d`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?c:d`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):c}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):c}
      </div>
    `}_heading(e){return d`<div class="section-heading">${f(this.hass,e)}</div>`}_subheading(e){return d`<div class="lighting-heading">${f(this.hass,e)}</div>`}_tile(e,t,i={}){return d`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${S(this.hass,e)}</span>
      </button>
    `}_onRowKey(e,t){e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),t())}_toggleRow(e){let i=this._state(e)?.state==="on",n=S(this.hass,e);return d`
      <div class="entity-row" @click=${()=>this._moreInfo(e)}>
        <button class="entity-row-details" @click=${r=>{r.stopPropagation(),this._moreInfo(e)}}>
          ${this._icon(e)}
          <div class="entity-row-text">
            <span>${n}</span>
            <span class="secondary">${this._stateText(e)}</span>
          </div>
        </button>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${n}
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(e)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_switchRow(e){let t=this._state(e);if(t?.attributes.assumed_state!==!0&&(t?.state==="on"||t?.state==="off"))return this._toggleRow(e);let i=S(this.hass,e),n=this._t("action.off"),r=this._t("action.on");return d`
      <div class="entity-row" role="group" aria-label=${i}>
        <button class="entity-row-details" aria-label=${i} @click=${()=>this._moreInfo(e)}>
          ${this._icon(e)}
          <span class="entity-row-text">
            <span>${i}</span>
            <span class="secondary">${this._stateText(e)}</span>
          </span>
        </button>
        <button class="dialog-btn" aria-label=${`${i}: ${n}`}
          @click=${()=>this._call("switch","turn_off",e)}>${n}</button>
        <button class="dialog-btn" aria-label=${`${i}: ${r}`}
          @click=${()=>this._call("switch","turn_on",e)}>${r}</button>
      </div>
    `}_moreInfoRow(e){let t=S(this.hass,e);return d`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${t}
        @click=${()=>this._moreInfo(e)}
        @keydown=${i=>this._onRowKey(i,()=>this._moreInfo(e))}
      >
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${t}</span>
        </div>
        <span class="secondary value">${this._stateText(e)}</span>
      </div>
    `}_icon(e,t){let i=this._state(e);return i?d`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:d`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return d`<ha-card><div class="notice">${f(this.hass,e)}</div></ha-card>`}_estimateSideKey(e,t){let i=[e.estimateRemote,e.stop,...e.motors.flatMap(n=>[n.estimate,n.reference])];for(let n of i){let r=n?this._state(n)?.attributes.bed_side:void 0;if(r==="left"||r==="right")return r}return t===0?"left":"right"}_t(e,t){return f(this.hass,e,t)}_contextEstimates(e){return e.sides.flatMap(t=>se(this.hass,t.motors))}_estimatesByKey(e){return Object.fromEntries(e.sides.map(t=>[t.key,se(this.hass,t.motors)]))}_estimateService(e,t,i={}){return this.hass?.callService(O,e,{device_id:t.deviceId,...t.side?{side:t.side}:{},...i})??Promise.resolve()}_toast(e){this.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:e},bubbles:!0,composed:!0}))}_positionHeading(e){let t=ct(e);return t?d`<div class="section-heading heading-row">
      <span>${this._t("section.position")}</span>
      <span class="estimate-chip chip-${t}">${this._t(`estimate.chip_${t}`)}</span>
    </div>`:this._heading("section.position")}_estimateValues(e){return e.map(t=>`${this._motorName({key:t.motor})} ${I({...t,state:t.percent===void 0?"unknown":"tracking"},(i,n)=>this._t(i,n))}`).join(", ")}_estimateAlertTemplate(e,t){let i=ti(t);if(!i)return c;let n,r,l=d`<button class="set-btn" @click=${()=>this._openReference(e)}>
      ${this._t("estimate.set_reference")}</button>`;if(i.kind==="calibrate")n=this._t("estimate.alert_calibrate"),r=d`<button class="set-btn" @click=${this._openSettings}>
        ${this._t("estimate.calibrate_now")}</button>`;else if(i.kind==="unconfirmed")n=this._t("estimate.alert_unconfirmed",{values:this._estimateValues(i.estimates)}),r=d`<button class="set-btn" @click=${()=>void this._estimateService("confirm_position_unchanged",e).catch(()=>{})}>
        ${this._t("estimate.unchanged")}</button>${l}`;else{let a=`estimate.reason_${i.reason??"not_referenced"}`,p=this._t(a);n=this._t("estimate.alert_unknown",{reason:p===a?this._t("estimate.reason_not_referenced"):p}),r=l}return d`<div class="estimate-alert alert-${i.kind}" role="status">
      <ha-icon icon=${i.kind==="calibrate"?"mdi:tune-variant":"mdi:alert-outline"}></ha-icon>
      <span class="estimate-alert-text">${n}</span>
      <div class="estimate-alert-actions">${r}</div>
    </div>`}_estimateOverview(e){let t=e.sides.flatMap(i=>{let n=se(this.hass,i.motors);return n.length?[{side:i,estimates:n}]:[]});return t.length===0?c:d`<div class="estimate-overview">
      ${t.map(({side:i,estimates:n})=>d`<div class="estimate-overview-row">
        <span class="estimate-overview-side">${i.label}</span>
        ${Oe(n)?d`<span>${n.map(r=>`${this._motorName({key:r.motor})} ${I(r,(l,a)=>this._t(l,a))}`).join(" \xB7 ")}</span>`:d`<span>${this._t("estimate.unknown")} ·
              <button class="link-btn" @click=${()=>this._openReference({deviceId:i.deviceId,paired:!0,sides:[i],savedPositions:e.savedPositions})}>${this._t("estimate.set_reference")}</button></span>`}
      </div>`)}
    </div>`}_savedPositions(e){if(!e.savedPositions)return c;let t=this._contextEstimates(e),i=si(ii(this.hass,e.savedPositions),e.sides.map(a=>a.key));if(t.length===0&&i.length===0)return c;let n=this._estimatesByKey(e),r=this._savedEditFor===e.deviceId,l=Oe(t);return d`
      <div class="section-heading heading-row">
        <span>${this._t("section.saved_positions")}</span>
        ${i.length?d`<button class="set-btn ${r?"active":""}"
              @click=${()=>{this._savedEditFor=r?void 0:e.deviceId}}>
              <ha-icon icon=${r?"mdi:check":"mdi:pencil-outline"}></ha-icon>
              <span>${this._t(r?"estimate.done":"estimate.edit")}</span>
            </button>`:c}
      </div>
      ${r?d`<div class="hint">${this._t("estimate.edit_hint")}</div>`:c}
      <div class="tiles">
        ${i.map(a=>{let p=ni(a,n),h=e.paired?oi(a):"bed";return d`<button
            class="tile ${r?"save-mode":""} ${!r&&!p?"is-disabled":""}"
            ?disabled=${!r&&!p}
            @click=${()=>r?this._openEdit(e,a):this._recall(e,a)}>
            <ha-icon class="icon" icon=${r?"mdi:pencil-outline":"mdi:bookmark-outline"}></ha-icon>
            <span class="tile-label">${a.name}</span>
            ${h!=="bed"?d`<span class="tile-sublabel">${this._t(`estimate.scope_${h}`)}</span>`:c}
          </button>`})}
        <button class="tile ${l?"":"is-disabled"}" ?disabled=${!l}
          @click=${()=>{this._estimateDialog={kind:"save",ctx:e,name:"",button:!0}}}>
          <ha-icon class="icon" icon="mdi:bookmark-plus-outline"></ha-icon>
          <span class="tile-label">${this._t("estimate.save")}</span>
        </button>
      </div>
      <div class="hint estimate-footer">${this._t("estimate.footer")}</div>
    `}_recall(e,t){this._hold.abandon(),this._estimateService("recall_position",{...e,side:void 0},{position:t.id}).then(()=>this._toast(this._t("estimate.recalled",{name:t.name}))).catch(()=>{})}_openReference(e){this._estimateDialog={kind:"reference",ctx:e,choice:"flat",phase:"choose"}}_openEdit(e,t){this._estimateDialog={kind:"edit",ctx:e,position:t,name:t.name,button:t.button}}_stopEstimate(e){this._estimateService("stop_all",e).catch(()=>{})}updated(e){super.updated(e),this._detailsCard&&(this._detailsCard.hass=this.hass);let t=this.renderRoot?.querySelector?.("dialog.estimate-dialog");t&&!t.open&&t.showModal()}_estimateDialogTemplate(){let e=this._estimateDialog;if(!e)return c;let t=e.kind==="confirm"?this._confirmDialog(e.entityId):e.kind==="reference"?this._referenceDialog(e):e.kind==="save"?this._saveDialog(e):this._editDialog(e);return d`<dialog class="estimate-dialog" @close=${this._closeEstimateDialog}>
      ${t}
    </dialog>`}_confirmDialog(e){let t=S(this.hass,e);return d`
      <p>${this._t("action.confirm",{action:t})}</p>
      <div class="dialog-actions">
        <button class="dialog-btn" @click=${this._closeEstimateDialog}>${this._t("memory.cancel")}</button>
        <button class="dialog-btn primary" @click=${()=>{this._closeEstimateDialog(),this._sendPress(e)}}>${t}</button>
      </div>`}_dialogMotors(e){let t=this._contextEstimates(e).filter(i=>i.state!=="not_calibrated").map(i=>i.motor);return[...new Set(t)]}_referenceDialog(e){let t=this._dialogMotors(e.ctx),i=t.map(h=>this._motorName({key:h})).join(", "),n=[{value:"flat",title:this._t("estimate.ref_flat"),detail:this._t(t.length===1?"estimate.ref_flat_detail_one":"estimate.ref_flat_detail",{motors:i})},{value:"lower",title:this._t("estimate.ref_lower"),detail:this._t("estimate.ref_lower_detail")},...t.length>1?t.map(h=>({value:`only:${h}`,title:this._t("estimate.ref_only",{motor:this._motorName({key:h})}),detail:this._t("estimate.ref_only_detail")})):[]],r=e.choice==="lower"&&e.phase==="choose",l=e.choice.startsWith("only:")?[e.choice.slice(5)]:t,a=()=>{if(e.phase!=="lowering"){if(r){let h={...e,phase:"lowering"};this._estimateDialog=h,this._estimateService("lower_to_flat",e.ctx).then(()=>{this._estimateDialog===h&&(this._estimateDialog={...e,phase:"lowered"})},()=>{this._estimateDialog===h&&(this._estimateDialog={...e,phase:"choose"})});return}this._estimateService("set_position_reference",e.ctx,{motors:l}).catch(()=>{}),this._estimateDialog=void 0}},p=e.phase==="lowering"?"estimate.ref_lowering_running":e.phase==="lowered"?"estimate.ref_lowering":"estimate.ref_text";return d`
      <h2>${this._t("estimate.ref_title")}</h2>
      <p class="dialog-text">${this._t(p)}</p>
      ${e.phase!=="choose"?c:d`<div class="dialog-choices" role="radiogroup">
        ${n.map(h=>d`<label class="dialog-choice">
          <input type="radio" name="reference" .checked=${e.choice===h.value}
            @change=${()=>{this._estimateDialog={...e,choice:h.value}}} />
          <span><strong>${h.title}</strong><span class="dialog-detail">${h.detail}</span></span>
        </label>`)}
      </div>`}
      <div class="dialog-actions">
        ${e.phase==="lowering"?d`<button class="dialog-btn danger" @click=${()=>{this._stopEstimate(e.ctx),this._estimateDialog={...e,phase:"choose"}}}>${this._t("action.stop")}</button>`:c}
        <button class="dialog-btn" @click=${this._closeEstimateDialog}>${this._t("memory.cancel")}</button>
        <button class="dialog-btn primary" ?disabled=${e.phase==="lowering"} @click=${a}>
          ${this._t(r?"estimate.ref_lower_start":"estimate.ref_confirm")}</button>
      </div>`}_estimateList(e){return d`<div class="dialog-values">
      ${e.sides.flatMap(t=>se(this.hass,t.motors).map(i=>d`
        <div class="dialog-value"><span>${e.paired?`${t.label} `:""}${this._motorName({key:i.motor})}</span>
          <span>${I(i,(n,r)=>this._t(n,r))}</span></div>`))}
    </div>`}_saveDialog(e){let t=e.name.trim(),i=()=>{t&&(this._estimateService("save_position",e.ctx,{name:t,create_button:e.button}).catch(()=>{}),this._estimateDialog=void 0)};return d`
      <h2>${this._t("estimate.save_title")}</h2>
      <label class="dialog-field"><span>${this._t("estimate.name")}</span>
        <input type="text" maxlength="40" .value=${e.name}
          @input=${n=>{this._estimateDialog={...e,name:n.target.value}}} />
      </label>
      ${this._estimateList(e.ctx)}
      <label class="dialog-check">
        <input type="checkbox" .checked=${e.button}
          @change=${n=>{this._estimateDialog={...e,button:n.target.checked}}} />
        <span><strong>${this._t("estimate.create_button")}</strong>
          <span class="dialog-detail">${this._t("estimate.create_button_detail")}</span></span>
      </label>
      <p class="dialog-text">${this._t("estimate.save_note")}</p>
      <div class="dialog-actions">
        <button class="dialog-btn" @click=${this._closeEstimateDialog}>${this._t("memory.cancel")}</button>
        <button class="dialog-btn primary" ?disabled=${!t} @click=${i}>${this._t("estimate.save_confirm")}</button>
      </div>`}_editDialog(e){let{position:t,ctx:i}=e,n=this._estimatesByKey(i),l=Object.keys(t.beds).every(u=>Oe(n[u]??[])),a=e.name.trim(),p=(u,m={})=>{this._estimateService(u,{...i,side:void 0},{position:t.id,...m}).catch(()=>{}),this._estimateDialog=void 0},h=u=>u==="bed"?"":`${this._t(`card.${u}_side`)} `;return d`
      <h2>${this._t("estimate.edit_title",{name:t.name})}</h2>
      <label class="dialog-field"><span>${this._t("estimate.name")}</span>
        <input type="text" maxlength="40" .value=${e.name}
          @input=${u=>{this._estimateDialog={...e,name:u.target.value}}} />
      </label>
      <div class="dialog-values">
        <div class="dialog-value dialog-value-head"><span></span>
          <span>${this._t("estimate.saved")}</span><span>${this._t("estimate.now")}</span></div>
        ${Object.entries(t.beds).flatMap(([u,m])=>Object.entries(m).map(([y,b])=>{let E=n[u]?.find(_=>_.motor===y);return d`<div class="dialog-value">
              <span>${h(u)}${this._motorName({key:y})}</span>
              <span>${Math.round(b)}%</span>
              <span>${E?I(E,(_,x)=>this._t(_,x)):"-"}</span>
            </div>`}))}
      </div>
      <label class="dialog-check">
        <input type="checkbox" .checked=${e.button}
          @change=${u=>{this._estimateDialog={...e,button:u.target.checked}}} />
        <span><strong>${this._t("estimate.create_button")}</strong>
          <span class="dialog-detail">${this._t("estimate.create_button_detail")}</span></span>
      </label>
      ${l?c:d`<p class="dialog-text">${this._t("estimate.update_blocked")}</p>`}
      <div class="dialog-actions">
        <button class="dialog-btn danger" @click=${()=>p("delete_position")}>${this._t("estimate.delete")}</button>
        <button class="dialog-btn" ?disabled=${!l} @click=${()=>p("update_position")}>${this._t("estimate.update")}</button>
        <button class="dialog-btn primary" ?disabled=${!a}
          @click=${()=>p("rename_position",{name:a,create_button:e.button})}>${this._t("estimate.save_confirm")}</button>
      </div>`}_state(e){return this.hass?.states[e]}_title(e=this._config?.device_id){return this._config?.name?this._config.name:L(this.hass,e)??f(this.hass,"card.default_name")}_motorName(e){let t=`motor.${e.key}`,i=f(this.hass,t);return i!==t?i:e.key.split("_").map(n=>n.charAt(0).toUpperCase()+n.slice(1)).join(" ")}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){let t=e.angle??e.position;if(t){let n=this._angle(e);if(n===void 0)return;let r=this._state(t)?.attributes.unit_of_measurement,l=e.angle?"\xB0":"%";return`${Math.round(n)}${typeof r=="string"?r:l}`}let i=be(this.hass,e);if(i)return I(i,(n,r)=>f(this.hass,n,r));if(e.cover){let n=this._state(e.cover)?.attributes.current_position;return typeof n=="number"?`${Math.round(n)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position,i.estimate,i.reference].forEach(n=>n&&t.add(n));[e.estimateRemote,e.savedPositions].forEach(i=>i&&t.add(i)),[...e.presets,...e.presetSaves].forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(n=>n&&t.add(n));return[e.stop,e.synchro,e.controlSide,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.state,...e.lights.states??[],e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.lights.timerMinutes,e.lights.timerToggle,e.lights.mood?.toggle,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.lights.buttons?.forEach(i=>t.add(i)),e.lights.numbers?.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.massage.selects?.forEach(i=>t.add(i)),e.massage.states?.forEach(i=>t.add(i)),e.massage.switches?.forEach(i=>t.add(i)),e.lights.switches?.forEach(i=>t.add(i)),e.lights.mood?.selects.forEach(i=>t.add(i)),e.lights.mood?.numbers.forEach(i=>t.add(i)),e.lights.mood?.buttons?.forEach(i=>t.add(i)),e.utility.forEach(i=>t.add(i)),e.utilityNumbers?.forEach(i=>t.add(i)),e.utilitySelects?.forEach(i=>t.add(i)),e.utilityStates?.forEach(i=>t.add(i)),e.utilitySwitches?.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),e.climate.numbers.forEach(i=>t.add(i)),[...t]}_startHold(e,t,i,n,r,l){let a=null;if(e instanceof KeyboardEvent){if(e.key!=="Enter"&&e.key!==" "||(e.preventDefault(),e.repeat))return}else{if(e.button!==0||!e.isPrimary)return;e.currentTarget.setPointerCapture?.(e.pointerId),e.preventDefault(),a=e.pointerId}if(this._hold.tapMoving){this._hold.endTap();return}this._markCompactTarget(t,n),this._hold.start(t,i,a,n,r??(n?[n]:[]),l,e instanceof KeyboardEvent?e.key:null,Q(this.hass,n??t.holdEntityId??t.cover??t[i]))}_activateWithoutPointer(e,t,i,n,r){if(e.detail===0){if(this._hold.tapMoving){this._hold.endTap();return}this._hold.heldKey===null&&(this._markCompactTarget(t,n),this._hold.claimStopScope([...r??[],...n?[n]:[],...t.cover?[t.cover]:[]],Q(this.hass,n??t.holdEntityId??t.cover??t[i])),xt(this.hass,t,i))}}_tapMove(e,t,i,n,r){this._hold.tapMoving||this._markCompactTarget(e,i),this._hold.tap(e,t,i,n??(i?[i]:[]),r,Q(this.hass,i??e.holdEntityId??e.cover??e[t]))}_markCompactTarget(e,t){this._config?.layout==="compact"&&(t?this._compactStopTargets.set(t,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate())}_endPointerHold(e,t,i){this._hold.endFromPointer(t,e.pointerId,e.type!=="pointerup"||e.button===0,i)}_endKeyHold(e,t,i){e.key!=="Enter"&&e.key!==" "||(e.stopPropagation(),this._hold.endKeyboard(t,i,e.key))}_endHold(e,t){this._hold.end(e,t)}_motorStop(e,t,i){if(this._hold.tapMoving&&this._hold.tapDirection(e)===void 0&&this._hold.endTap(),e.cover){i?.length?Te(this._hold,e.cover,[...i,e.cover],e.coverStopScope==="side"?void 0:e.key,this.hass):(this._hold.stopCover(e,Q(this.hass,e.cover),e.coverStopScope??"motor",t,We(this.hass,e.cover)),this._cover(e.cover,"stop_cover"));return}Te(this._hold,t,i,void 0,this.hass)}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){if(this.hass?.states[e]?.attributes.requires_confirmation===!0){this._estimateDialog={kind:"confirm",entityId:e};return}this._sendPress(e)}_sendPress(e){this._hold.retireTap(),this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_setEntities(e,t){this.hass?.callService("homeassistant",t?"turn_on":"turn_off",{entity_id:e})?.catch(()=>{})}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};M.styles=de`
    .bed-details-dialog {
      box-sizing: border-box;
      width: min(560px, calc(100vw - 24px));
      max-height: calc(100dvh - 32px);
      padding: 0;
      overflow: auto;
      color: var(--primary-text-color);
      background: var(--card-background-color, #fff);
      border: 1px solid var(--divider-color);
      border-radius: 16px;
      box-shadow: 0 16px 60px #0006;
    }
    .bed-details-dialog::backdrop { background: #0009; }
    .bed-details-heading {
      position: sticky; top: 0; z-index: 1;
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px; padding: 8px 16px;
      background: var(--card-background-color, #fff);
      border-bottom: 1px solid var(--divider-color);
    }
    .bed-details-close {
      border: 0; background: transparent; color: inherit;
      width: 44px; height: 44px; font-size: 20px; cursor: pointer;
    }
    .bed-details-content { padding: 8px; }
    .compact-card { padding: 13px; }
    .compact-header { display: grid; grid-template-columns: minmax(0, 1fr) 24px;
      align-items: center; gap: 8px; min-height: 22px; padding: 0 2px 9px; }
    .compact-header .title { font-size: 14px; line-height: 22px; font-weight: 700; }
    .compact-open { display: grid; place-items: center; padding: 0; border: 0;
      background: none; color: var(--secondary-text-color); cursor: pointer;
      width: 24px; height: 22px; }
    .compact-open ha-icon { --mdc-icon-size: 16px; }
    .compact-card .compact-tabs { margin: 0; }
    .compact-tabs .pane-tab {
      min-height: 38px; height: auto; padding: 4px 5px; gap: 4px;
      font-size: 11px;
    }
    .compact-tabs .dual-swatch, .compact-readouts .dual-swatch { width: 6px; height: 6px; }
    .compact-tabs .compact-tab-label { min-width: 0; }
    .compact-target { color: var(--secondary-text-color); font-size: .8rem; padding: 6px 0; }
    .compact-graphic { position: relative; display: block; box-sizing: border-box; width: 100%; padding: 0;
      border: 0; border-radius: 8px; background: none; color: var(--primary-text-color); }
    button.compact-graphic { cursor: pointer; }
    .compact-estimate-chip { position: absolute; top: 0; right: 0; }
    .compact-graphic .bed-graphic { display: block; width: 100%; height: 132px; max-width: 300px; margin: auto; }
    .compact-glance .compact-graphic .bed-graphic { height: 112px; }
    .compact-no-position { min-height: 90px; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 8px; font-size: .75rem;
      color: var(--secondary-text-color); }
    .compact-no-position ha-icon { --mdc-icon-size: 36px; }
    .compact-readouts { display: flex; justify-content: space-between; gap: 8px;
      padding: 0 2px 12px; font-size: 11px; line-height: 17px; color: var(--secondary-text-color); }
    .compact-readouts > div { min-width: 0; display: flex; align-items: center; gap: 5px; }
    .compact-side-name { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
    .compact-side-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden;
      clip-path: inset(50%); white-space: nowrap; }
    .compact-names { justify-content: center; flex-wrap: wrap; gap: 19px; padding: 4px 0 3px; }
    .compact-position { font-weight: 500; overflow-wrap: anywhere; }
    .side-theme .dual-swatch { background: var(--primary-color); }
    .compact-card .compact-actions { grid-template-columns: repeat(auto-fit, minmax(64px, 1fr)); gap: 7px; }
    .compact-actions .tile { min-height: 54px; padding: 5px 4px; gap: 2px;
      justify-content: center; }
    .compact-actions .tile .icon, .compact-actions .tile ha-icon { --mdc-icon-size: 22px; }
    .compact-actions .tile-label { font-size: 11px; line-height: 17px;
      white-space: normal; overflow-wrap: anywhere; }
    .compact-stop ha-icon { color: var(--error-color); }
    .compact-actions .tile:disabled { opacity: .45; cursor: default; }
    .compact-card .compact-motors { gap: 6px; margin: 0 0 10px; }
    .compact-motors .row { padding: 0; border: 0; border-radius: 0; gap: 6px; }
    .compact-motors .row-label { font-size: 12px; }
    .compact-connections { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px;
      font-size: .72rem; color: var(--secondary-text-color); }
    .compact-connections > span { display: inline-flex; align-items: center; gap: 5px; }
    .no-animation .bed-panel, .no-animation .dual-bed-panel { transition: none; }
    button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    @container bed-card (max-width: 258px) {
      .compact-card { padding: 10px; }
      .compact-header { min-height: 19px; }
      .compact-header .title { font-size: 12px; line-height: 19px; }
      .compact-open { height: 19px; }
      .compact-graphic .bed-graphic { height: 96px; }
      .compact-readouts { font-size: 9px; line-height: 14px; gap: 3px; padding-bottom: 10px; }
      .compact-tabs .pane-tab { min-height: 34px; font-size: 10px; }
      .compact-actions .tile { min-height: 44px; padding: 2px 3px; }
      .compact-actions .tile-label { font-size: 10px; line-height: 15px; }
      .compact-actions .tile .icon, .compact-actions .tile ha-icon { --mdc-icon-size: 20px; }
    }
    @media (prefers-reduced-motion: reduce) {
      :host .bed-panel, :host .dual-bed-panel { transition: none; }
      :host .pane { animation: none; }
    }

    :host {
      display: block;
      container: bed-card / inline-size;
      --ab-gap: 10px;
      --ab-control-surface: color-mix(in srgb, var(--card-background-color) 94%, var(--primary-text-color));
      --ab-control-border: color-mix(in srgb, var(--card-background-color) 85%, var(--primary-text-color));
      --ab-side-left-rgb: 115, 182, 237;
      --ab-side-right-rgb: 237, 144, 158;
    }
    ha-card {
      padding: 12px 12px 16px;
      overflow: hidden;
    }
    .header {
      /* Reserve the optional Bluetooth action across paired tab changes. */
      display: grid;
      grid-template-columns: 22px minmax(0, 1fr) 32px;
      min-height: 32px;
      align-items: center;
      gap: 10px;
      padding: 4px 4px 8px;
    }
    .header-icon {
      color: var(--state-icon-color, var(--primary-text-color));
      --mdc-icon-size: 22px;
    }
    .title {
      font-size: 1rem;
      font-weight: 700;
      color: var(--primary-text-color);
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .conn {
      box-sizing: border-box;
      width: 32px;
      height: 32px;
      align-items: center;
      justify-content: center;
      border: none;
      background: none;
      cursor: pointer;
      padding: 4px;
      border-radius: 50%;
      display: inline-flex;
      --mdc-icon-size: 20px;
    }
    .conn.ok {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .conn.connecting {
      color: var(--warning-color, var(--state-active-color, #ff9800));
    }
    .conn.idle {
      color: var(--info-color, var(--secondary-text-color));
    }
    .conn.off {
      color: var(--secondary-text-color);
    }
    .section-heading {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--secondary-text-color);
      padding: 14px 4px 8px;
    }
    .lighting-heading {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--secondary-text-color);
      padding: 12px 4px 4px;
    }
    .pane-tabs {
      display: grid;
      grid-template-columns: repeat(var(--pane-count, 3), minmax(0, 1fr));
      gap: 3px;
      padding: 3px;
      margin: 0 0 6px;
      border-radius: 9px;
      background: color-mix(in srgb, var(--card-background-color) 45%,
        var(--primary-background-color, var(--card-background-color)));
    }
    .pane-tab {
      min-width: 0;
      min-height: 44px;
      padding: 4px 8px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--primary-text-color);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      font: inherit;
      font-size: .8rem;
      font-weight: 400;
      transition: background .15s ease;
      user-select: none;
      touch-action: manipulation;
    }
    .pane-tab .dual-swatch { width: 6px; height: 6px; }
    .pane-tab span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .pane-tab:hover { background: var(--ab-control-surface); }
    .pane-tab.active {
      background: color-mix(in srgb, var(--secondary-background-color), var(--primary-color) 12%);
    }
    .connection-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--disabled-text-color);
      flex: none;
    }
    .connection-dot.connected {
      background: var(--success-color, var(--state-active-color, #43a047));
    }
    .connection-dot.connecting {
      background: var(--warning-color, var(--state-active-color, #ff9800));
    }
    .connection-dot.idle {
      background: var(--info-color, var(--secondary-text-color));
    }
    .connection-dot.disconnected {
      background: var(--error-color);
    }
    .pane {
      animation: ab-pane-in 0.16s ease-out;
    }
    @keyframes ab-pane-in {
      from {
        opacity: 0;
        transform: translateY(2px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    .heading-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .set-btn {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border: 1px solid var(--ab-control-border);
      background: var(--ab-control-surface);
      color: var(--primary-color);
      border-radius: 999px;
      padding: 4px 12px 4px 9px;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: none;
      cursor: pointer;
      --mdc-icon-size: 16px;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    .set-btn:hover {
      background: var(--secondary-background-color);
    }
    .set-btn.active {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .hint {
      font-size: 0.8rem;
      color: var(--secondary-text-color);
      padding: 0 6px 8px;
    }
    .tile.save-mode {
      border-color: var(--primary-color);
      border-style: dashed;
    }
    .tile.save-mode .icon {
      color: var(--primary-color);
    }
    .tile.is-disabled {
      opacity: 0.4;
      cursor: default;
    }
    .graphic {
      display: flex;
      justify-content: center;
      padding: 4px 8px 0;
    }
    .bed-graphic {
      width: 100%;
      max-width: 350px;
      height: auto;
      overflow: visible;
    }
    .bed-graphic-theme {
      --ab-graphic-rgb: var(--rgb-primary-color, 33, 150, 243);
    }
    .bed-graphic-left {
      --ab-graphic-rgb: var(--ab-side-left-rgb);
    }
    .bed-graphic-right {
      --ab-graphic-rgb: var(--ab-side-right-rgb);
    }
    .bed-graphic.is-moving {
      opacity: 0.95;
    }
    /* How a panel's position is known (#601). Only measured feedback is solid.
       Set per panel, so a lumbar section follows the same rule. */
    .bed-panel.is-estimated .bed-surface,
    .dual-bed-panel.is-estimated .dual-bed-surface {
      fill-opacity: 0.45;
      stroke-width: 1.5;
      stroke-dasharray: 5 4;
    }
    .bed-panel.is-estimated .bed-surface { stroke: rgb(var(--ab-graphic-rgb)); }
    .dual-bed-panel.is-estimated .dual-bed-surface { stroke: currentColor; }
    .is-unconfirmed .bed-surface,
    .is-unconfirmed .dual-bed-surface {
      fill: var(--secondary-text-color);
      fill-opacity: 0.3;
      stroke: var(--secondary-text-color);
      stroke-width: 1.5;
      stroke-dasharray: 5 4;
    }
    .is-unknown .bed-surface,
    .is-unknown .dual-bed-surface {
      fill-opacity: 0.08;
      stroke: var(--secondary-text-color);
      stroke-width: 1.5;
      stroke-dasharray: 1 3;
      stroke-linecap: round;
    }
    .estimate-chip {
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 0.66rem;
      letter-spacing: 0.06em;
      background: color-mix(in srgb, var(--primary-color) 16%, transparent);
      color: var(--primary-color);
    }
    .estimate-chip.chip-unconfirmed,
    .estimate-chip.chip-unknown {
      background: color-mix(in srgb, var(--warning-color, #ffa600) 18%, transparent);
      color: var(--warning-color, #ffa600);
    }
    .estimate-alert {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 6px 10px;
      align-items: start;
      margin: 10px 2px 2px;
      padding: 10px 12px;
      border-radius: 9px;
      background: color-mix(in srgb, var(--warning-color, #ffa600) 12%, transparent);
      color: var(--primary-text-color);
      font-size: 0.82rem;
      --mdc-icon-size: 20px;
    }
    .estimate-alert.alert-calibrate {
      background: color-mix(in srgb, var(--primary-color) 12%, transparent);
    }
    .estimate-alert > ha-icon {
      color: var(--warning-color, #ffa600);
    }
    .estimate-alert.alert-calibrate > ha-icon {
      color: var(--primary-color);
    }
    .estimate-alert-actions {
      grid-column: 2;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .estimate-overview {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 0 6px 8px;
      font-size: 0.82rem;
    }
    .estimate-overview-row {
      display: flex;
      gap: 10px;
    }
    .estimate-overview-side {
      font-weight: 600;
      min-width: 3.5em;
    }
    .link-btn {
      border: none;
      background: none;
      padding: 0;
      color: var(--primary-color);
      font: inherit;
      cursor: pointer;
      text-decoration: underline;
    }
    .tile-sublabel {
      font-size: 0.68rem;
      color: var(--secondary-text-color);
    }
    .estimate-dialog {
      box-sizing: border-box;
      width: min(92vw, 420px);
      border: none;
      border-radius: 16px;
      padding: 20px;
      background: var(--card-background-color, var(--primary-background-color));
      color: var(--primary-text-color);
      font-size: 0.9rem;
    }
    .estimate-dialog::backdrop {
      background: rgba(0, 0, 0, 0.5);
    }
    .estimate-dialog h2 {
      margin: 0 0 8px;
      font-size: 1.15rem;
      font-weight: 500;
    }
    .dialog-text,
    .dialog-detail {
      color: var(--secondary-text-color);
    }
    .dialog-detail {
      display: block;
      font-size: 0.8rem;
    }
    .dialog-choices {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 10px 0;
    }
    .dialog-choice,
    .dialog-check {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      cursor: pointer;
    }
    .dialog-check {
      margin: 12px 0 4px;
    }
    .dialog-field {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin: 8px 0;
    }
    .dialog-field input {
      font: inherit;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid var(--divider-color);
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
    }
    .dialog-values {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin: 10px 0;
    }
    .dialog-value {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 12px;
    }
    .dialog-value-head {
      color: var(--secondary-text-color);
      font-size: 0.78rem;
    }
    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }
    .dialog-btn {
      font: inherit;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid var(--divider-color);
      background: none;
      color: var(--primary-color);
      cursor: pointer;
    }
    .dialog-btn.primary {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .dialog-btn.danger {
      color: var(--error-color);
      margin-right: auto;
    }
    .dialog-btn:disabled {
      opacity: 0.4;
      cursor: default;
    }
    .bed-frame-stop {
      stop-color: var(--secondary-text-color);
    }
    .bed-graphic-theme .bed-mattress-stop {
      stop-color: rgb(var(--rgb-primary-color, 33, 150, 243));
    }
    .bed-graphic-left .bed-mattress-stop,
    .dual-bed-left-stop {
      stop-color: rgb(var(--ab-side-left-rgb));
    }
    .bed-graphic-right .bed-mattress-stop,
    .dual-bed-right-stop {
      stop-color: rgb(var(--ab-side-right-rgb));
    }
    .bed-frame,
    .dual-bed-frame {
      fill: var(--secondary-text-color);
      opacity: .55;
      stroke: none;
    }
    .bed-side-layer {
      opacity: 0.86;
    }
    .bed-graphic-left .bed-side-layer,
    .bed-graphic-right .bed-side-layer {
      opacity: 0.66;
    }
    .bed-surface,
    .dual-bed-surface {
      stroke: var(--primary-text-color);
      stroke-opacity: .65;
      stroke-width: .7px;
      vector-effect: non-scaling-stroke;
    }
    .dual-bed-left-stop, .dual-bed-right-stop { stop-opacity: 1; }
    .bed-pillow,
    .dual-bed-pillow {
      opacity: 0.9;
    }
    .bed-panel {
      transition: transform 0.55s cubic-bezier(0.2, 0.7, 0.2, 1);
    }
    .bed-graphic-label {
      fill: var(--secondary-text-color);
      font-size: 11px;
      font-family: var(--ha-font-family-body, var(--primary-font-family, sans-serif));
    }
    .dual-graphic {
      padding-top: 8px;
    }
    .dual-bed-graphic {
      isolation: isolate;
    }
    .dual-bed-side {
      opacity: 0.66;
    }
    .dual-bed-panel {
      transition: transform 0.55s cubic-bezier(0.2, 0.7, 0.2, 1);
    }
    .dual-bed-side.is-moving {
      stroke-width: 1.5;
    }
    .dual-readouts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      width: min(100%, 350px);
      margin: -2px auto 2px;
    }
    .dual-readout {
      min-width: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
      padding: 8px 10px;
      text-align: center;
    }
    .dual-side-name {
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--primary-text-color);
      font-size: 0.8rem;
      font-weight: 600;
    }
    .dual-swatch {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex: none;
    }
    .side-left .dual-swatch {
      background: rgb(var(--ab-side-left-rgb));
    }
    .side-right .dual-swatch {
      background: rgb(var(--ab-side-right-rgb));
    }
    .dual-position {
      overflow: hidden;
      color: var(--secondary-text-color);
      font-size: 0.72rem;
      line-height: 1.25;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-row {
      box-sizing: border-box;
      width: min(100%, 350px);
      min-height: 52px;
      margin: 4px auto 2px;
      padding: 7px 9px;
      display: flex;
      align-items: center;
      gap: 8px;

      border-radius: 11px;

    }
    .dual-sync-row > ha-icon {
      flex: none;
      color: var(--secondary-text-color);
      --mdc-icon-size: 19px;
    }
    .dual-sync-label {
      min-width: 0;
      flex: 1;
      color: var(--primary-text-color);
      font-size: 0.78rem;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 4px;
      min-width: 148px;
      max-width: 52%;
      flex: none;
    }
    .dual-sync-btn {
      min-width: 0;
      height: 34px;
      padding: 0 9px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      border: 1px solid var(--ab-control-border);
      border-radius: 9px;
      background: var(--ab-control-surface);
      color: var(--primary-text-color);
      font: inherit;
      font-size: 0.74rem;
      font-weight: 500;
      cursor: pointer;
      transition: border-color 0.15s ease, background 0.15s ease, opacity 0.15s ease;
    }
    .dual-sync-btn:hover:not(:disabled),
    .dual-sync-btn:focus-visible {
      border-color: var(--primary-color);
    }
    .dual-sync-btn:disabled {
      cursor: default;
      opacity: 0.42;
    }
    .dual-sync-btn.is-active {
      opacity: 1;
      border-color: var(--primary-color);
      background: var(--secondary-background-color);
    }
    .dual-sync-btn span:last-child {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-spinner {
      flex: none;
      color: var(--primary-color);
      --mdc-icon-size: 15px;
    }
    .dual-sync-error {
      box-sizing: border-box;
      width: min(100%, 350px);
      margin: 5px auto 2px;
      padding: 6px 9px;
      display: flex;
      align-items: center;
      gap: 6px;
      border-radius: 9px;
      background: color-mix(in srgb, var(--error-color) 12%, transparent);
      color: var(--error-color);
      font-size: 0.72rem;
    }
    .dual-sync-error ha-icon {
      flex: none;
      --mdc-icon-size: 16px;
    }



    .rows {
      display: flex;
      flex-direction: column;
      gap: var(--ab-gap);
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      padding: 6px 0;
    }
    .row-label {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-width: 90px;
    }
    .row-label .readout {
      color: var(--secondary-text-color);
      font-size: 0.82rem;
    }
    .position-label {
      border: 0;
      border-radius: 4px;
      padding: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      text-align: start;
      cursor: pointer;
    }
    .position-label .readout {
      color: var(--primary-color);
      text-decoration: underline dotted;
      text-underline-offset: 3px;
    }
    .control-group { display: inline-flex; gap: 6px; }
    .cg-btn {
      box-sizing: border-box;
      width: 44px;
      height: 44px;
      border: 1px solid var(--ab-control-border);
      border-radius: 8px;
      background: var(--ab-control-surface);
      color: var(--primary-color);
      cursor: pointer;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      --mdc-icon-size: 22px;
      transition: background 0.15s ease;
      /* Press-and-hold has to survive a slightly unsteady finger. Pointer
         capture and preventDefault() do not override the browser's touch
         gesture arbitration, so without this a small vertical drag starts
         scrolling the page, fires pointercancel and cuts the hold short. */
      touch-action: none;
    }
    .cg-btn:hover {
      background: var(--secondary-background-color);
    }
    .cg-btn:active {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.18);
    }
    .cg-btn[disabled] {
      color: var(--disabled-text-color);
      cursor: default;
    }
    /* A tap move starts on click, so a drag that begins on the arrow may
       scroll the page instead. */
    .cg-btn.tap {
      touch-action: manipulation;
    }
    .cg-btn.moving,
    .cg-btn.moving:hover {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .row-label .readout.moving {
      color: var(--primary-color);
    }
    .stop-all {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      margin-top: var(--ab-gap);
      padding: 10px;
      border-radius: 9px;
      cursor: pointer;
      background: var(--ab-control-surface);
      border: 1px solid var(--ab-control-border);
      color: var(--error-color);
      font-size: 0.9rem;
      font-weight: 500;
      --mdc-icon-size: 20px;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    .stop-all:hover {
      background: var(--secondary-background-color);
    }
    .stop-all:active,
    .stop-all[data-armed] {
      border-color: var(--error-color);
    }
    /* A tap move is running and waits for a tap to stop it. */
    .stop-all[data-armed] {
      background: color-mix(in srgb, var(--error-color) 12%, var(--ab-control-surface));
    }
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
      gap: var(--ab-gap);
    }
    .tile {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      justify-content: center;
      min-height: 64px;
      padding: 8px 6px;
      background: var(--ab-control-surface);
      border: 1px solid var(--ab-control-border);
      border-radius: 9px;
      cursor: pointer;
      color: var(--primary-text-color);
      transition: background 0.15s ease, border-color 0.15s ease;
      -webkit-user-select: none;
      user-select: none;
      touch-action: manipulation;
    }
    .tile:hover {
      background: var(--secondary-background-color);
    }
    .tile:active {
      border-color: var(--primary-color);
    }
    .tile .icon {
      color: var(--primary-color);
      --mdc-icon-size: 22px;
    }
    .tile.danger .icon {
      color: var(--error-color);
    }
    .tile.success .icon {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .tile-label {
      font-size: 0.78rem;
      text-align: center;
      line-height: 1.2;
    }
    .entity-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 12px;
      background: var(--ab-control-surface);
      border: 1px solid var(--ab-control-border);
      border-radius: 9px;
      cursor: pointer;
      margin-bottom: var(--ab-gap);
    }
    .entity-row .icon {
      color: var(--state-icon-color, var(--primary-color));
      --mdc-icon-size: 24px;
    }
    .combined-entity-row {
      cursor: default;
    }
    .combined-entity-row .icon.active {
      color: var(--state-light-active-color, var(--state-active-color, #ffc107));
    }
    .entity-row-text {
      display: flex;
      flex-direction: column;
      flex: 1;
    }
    .entity-row-details {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;
      min-width: 0;
      padding: 0;
      border: none;
      background: none;
      color: inherit;
      font: inherit;
      text-align: start;
      cursor: pointer;
    }
    .entity-row-text .secondary,
    .value {
      color: var(--secondary-text-color);
      font-size: 0.82rem;
    }
    .toggle {
      width: 42px;
      height: 24px;
      border-radius: 12px;
      border: none;
      background: var(--switch-unchecked-track-color, rgba(120, 120, 120, 0.4));
      position: relative;
      cursor: pointer;
      padding: 0;
      transition: background 0.2s ease;
      flex: none;
    }
    .toggle.on {
      background: var(--primary-color);
    }
    .toggle.mixed {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.55);
    }
    .toggle .knob {
      position: absolute;
      top: 2px;
      left: 2px;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--switch-unchecked-button-color, #fff);
      transition: transform 0.2s ease;
    }
    .toggle.on .knob {
      transform: translateX(18px);
    }
    .bluetooth-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--ab-gap);
    }
    .bluetooth-receiver {
      min-width: 0;
      display: grid;
      gap: var(--ab-gap);
    }
    .bluetooth-status {
      min-width: 0;
      width: 100%;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--ab-control-border);
      border-radius: 9px;
      background: var(--ab-control-surface);
      color: var(--primary-text-color);
      cursor: pointer;
      font: inherit;
      text-align: left;
    }
    .bluetooth-status ha-icon {
      --mdc-icon-size: 22px;
      flex: none;
    }
    .bluetooth-status.connected ha-icon {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .bluetooth-status.connecting ha-icon {
      color: var(--warning-color, var(--state-active-color, #ff9800));
    }
    .bluetooth-status.idle ha-icon {
      color: var(--info-color, var(--secondary-text-color));
    }
    .bluetooth-status.disconnected ha-icon {
      color: var(--secondary-text-color);
    }
    .bluetooth-copy {
      min-width: 0;
      display: flex;
      flex-direction: column;
    }
    .bluetooth-detail {
      overflow: hidden;
      color: var(--secondary-text-color);
      font-size: 0.72rem;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .notice {
      padding: 24px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }
  `,T([oe({attribute:!1})],M.prototype,"hass",2),T([P()],M.prototype,"_config",2),T([P()],M.prototype,"_saveModeFor",2),T([P()],M.prototype,"_activePairedPane",2),T([P()],M.prototype,"_synchronizingTo",2),T([P()],M.prototype,"_synchronizationFailed",2),T([P()],M.prototype,"_estimateDialog",2),T([P()],M.prototype,"_savedEditFor",2),T([P()],M.prototype,"_tapRevision",2),T([P()],M.prototype,"_detailsOpen",2);Ae("adjustable-bed-card",M);console.info(`%c adjustable-bed-card %c ${_i} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{M as AdjustableBedCard};
