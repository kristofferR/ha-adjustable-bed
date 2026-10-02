/* adjustable-bed-card 4.0.2 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var le=Object.defineProperty;var de=Object.getOwnPropertyDescriptor;var $=(n,o,t,e)=>{for(var i=e>1?void 0:e?de(o,t):o,s=n.length-1,r;s>=0;s--)(r=n[s])&&(i=(e?r(o,t,i):r(i))||i);return e&&i&&le(o,t,i),i};var P="adjustable_bed";function K(n){for(let o of["left","right","both"]){let t=`_${o}`;if(n.endsWith(t))return{key:n.slice(0,-t.length),side:o}}return{key:n}}var D=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],Ot=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],_t=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_swing","preset_incline","preset_both_up","preset_yoga"],pe=n=>n.split(".",1)[0],bt=n=>n.translation_key??"";function he(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[]}}function x(n,o,t){let e=he();if(!o||!n?.entities)return e;let i=()=>e.lights.mood??={selects:[],numbers:[]},s=n.devices?.[o]?.parent_device_id||Object.values(n.devices??{}).some(m=>m.parent_device_id===o),r=new Map,a=m=>{let h=r.get(m);return h||(h={key:m},r.set(m,h)),h},c=new Map,u=new Map,_=m=>{let h=u.get(m);return h||(h={slot:m},u.set(m,h)),h};for(let m of Object.values(n.entities)){if(m.device_id!==o||m.platform!==P||m.hidden)continue;let h=m.entity_id,b=pe(h),j=bt(m);if(!j)continue;let L=K(j),ce=n.states[h]?.attributes.bed_side??n.states[h]?.attributes.side??L.side;if(t&&ce!==t)continue;let d=t||s?L.key:j,T;switch(b){case"cover":a(d).cover=h;break;case"sensor":d.endsWith("_angle")&&(a(d.slice(0,-6)).angle=h);break;case"number":d.endsWith("_position")?a(d.slice(0,-9)).position=h:!t&&L.side&&L.key.endsWith("_position")?a(`${L.key.slice(0,-9)}_${L.side}`).position=h:d.startsWith("massage_")&&d.endsWith("_intensity")?e.massage.numbers.push(h):d==="light_level"||d==="starcode_brightness"||d==="vmatbasic_floor_level"||d==="starcode_abm5_4_light_level"?e.lights.level=h:d==="vmatbasic_floor_minutes"?(e.lights.timerMinutes=h,e.lights.timerAppliesImmediately=!0):d==="vibradorm_app_floor_timer_minutes"?e.lights.timerMinutes=h:d==="vibradorm_app_mood_speed"||d==="vmatbasic_mood_speed"||d==="vmatbasic_mood_brightness"?i().numbers.push(h):d==="vibradorm_app_massage_speed"?e.massage.numbers.push(h):d==="fan_level"?e.climate.numbers.push(h):d.startsWith("sleep_number_setting")&&e.firmness.push(h);break;case"button":_t.includes(d)||d.startsWith("preset_")?(T=d.match(/^preset_memory_(\d+)$/))?_(Number(T[1])).goto=h:c.set(d,h):(T=d.match(/^program_memory_(\d+)$/))?_(Number(T[1])).save=h:d==="stop"||d==="stop_both"?e.stop=h:d==="connect"?e.connect=h:d==="disconnect"?e.disconnect=h:d==="toggle_light"?e.lights.toggle=h:d==="light_cycle"||d==="starcode_light_cycle"?e.lights.cycle=h:d==="vibradorm_app_mood_toggle"||d==="vmatbasic_mood_toggle"?i().toggle=h:d==="vmatbasic_mood_nightlight"?(i().buttons??=[]).push(h):d==="vmatbasic_floor_toggle"||d==="vmatbasic_floor_hold"?e.lights.toggle=h:d.startsWith("vmatbasic_massage_")?e.massage.buttons.push(h):d==="vibradorm_app_floor_timer_toggle"?e.lights.timerToggle=h:d==="starcode_abm5_4_light_plus"||d==="starcode_abm5_4_light_minus"||d==="starcode_abm5_4_light_on"||d==="starcode_abm5_4_light_off"?(e.lights.buttons??=[]).push(h):d==="starcode_abm5_4_massage_release"?e.massage.buttons.push(h):d.startsWith("starcode_abm5_4_")?e.utility.push(h):d.startsWith("simmons_inclined_")?c.set(d,h):d==="simmons_sync_clock"||d==="simmons_refresh_alarms"?e.utility.push(h):d==="coolbase_head_massage"||d==="coolbase_foot_massage"||d==="coolbase_massage_mode"?e.massage.buttons.push(h):d.startsWith("coolbase_")?e.utility.push(h):d==="vibradorm_app_massage_automatic"||d==="vibradorm_app_massage_individual"?e.massage.buttons.push(h):d==="sync_positions"||d==="child_lock_toggle"||d==="auxiliary_action"||d==="remote_action"||d==="solace_music_toggle"||d==="solace_music_off"||d==="wake_controller"||d==="reset_defaults"||d==="factory_reset"||d==="vibradorm_app_all_up"||d==="vibradorm_app_all_down"||d==="vibradorm_app_sync"||d==="vibradorm_app_refresh_info"||d==="vmatbasic_all_up"||d==="vmatbasic_all_down"||d==="vmatbasic_refresh_info"||d.startsWith("starcode_save_")||d==="starcode_reset"||d==="starcode_query"||d==="starcode_light_mode"?e.utility.push(h):d.startsWith("massage_")?e.massage.buttons.push(h):(T=d.match(/^(.+)_(up|down)$/))&&(a(T[1])[T[2]]=h);break;case"switch":d==="under_bed_lights"?e.lights.switch=h:d==="synchro_mode"?e.synchro=h:(d==="linak_automatic_drive"||d==="automatic_light")&&e.utility.push(h);break;case"light":e.lights.light=h;break;case"binary_sensor":d==="ble_connection"?e.connectivity=h:d==="under_bed_lights"||d==="adjustable_lite_light"?e.lights.state=h:d.startsWith("bed_presence")&&e.presence.push(h);break;case"select":d==="motion_bed_active_module"?(e.utilitySelects??=[]).push(h):d==="light_timer"?e.lights.timer=h:d==="starcode_color"||d==="vibradorm_app_mood_palette"||d==="vibradorm_app_mood_effect"||d==="vmatbasic_mood_palette"||d==="vmatbasic_mood_effect"?i().selects.push(h):d==="vibradorm_app_massage_wave"?(e.massage.selects??=[]).push(h):d==="massage_timer"||d==="starcode_abm5_4_massage_timer"?e.massage.timer=h:/thermal|footwarming|foundation/.test(d)&&e.climate.selects.push(h);break;case"climate":e.climate.entities.push(h);break}}let f=[...r.keys()],v=[...Ot.filter(m=>r.has(m)),...f.filter(m=>!Ot.includes(m)).sort()];e.motors=v.map(m=>r.get(m)).filter(m=>m.cover||m.up||m.down||m.angle||m.position);let y=[...c.keys()];return e.presets=[..._t.filter(m=>c.has(m)),...y.filter(m=>!_t.includes(m)).sort()].map(m=>c.get(m)),e.memory=[...u.values()].filter(m=>m.goto||m.save).sort((m,h)=>m.slot-h.slot),e}function it(n,o){return!o||!n?.entities?!1:Object.values(n.entities).some(t=>t.device_id===o&&t.platform===P&&(n.states[t.entity_id]?.attributes.bed_side==="both"||K(bt(t)).side==="both"))}function W(n,o){if(!o||!n?.devices)return[];let t=i=>{let s=n.devices[i];return(s?.name_by_user??s?.name??i).toLowerCase()},e=i=>{for(let s of Object.values(n.entities??{})){if(s.device_id!==i||s.platform!=="adjustable_bed")continue;let r=n.states[s.entity_id]?.attributes.bed_side??K(bt(s)).side;if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(n.devices).filter(i=>(i.parent_device_id??i.via_device_id)===o).map(i=>i.id).sort((i,s)=>e(i)-e(s)||t(i).localeCompare(t(s)))}function ot(n,o){if(!o||!n?.devices)return o;let t=n.devices[o]?.parent_device_id??n.devices[o]?.via_device_id;return t&&n.devices[t]&&W(n,t).length?t:o}function S(n){let o=n.lights;return n.motors.length===0&&!n.synchro&&n.firmness.length===0&&n.presets.length===0&&n.memory.length===0&&!n.stop&&!n.connect&&!n.disconnect&&!n.connectivity&&!N(o)&&!o.state&&n.massage.buttons.length===0&&n.massage.numbers.length===0&&!n.massage.selects?.length&&!n.massage.timer&&n.climate.entities.length===0&&n.climate.selects.length===0&&n.climate.numbers.length===0&&n.utility.length===0&&!n.utilitySelects?.length}function N(n){return!!(n.light||n.switch||n.level||n.toggle||n.buttons?.length||n.cycle||n.timer||n.timerMinutes||n.timerToggle||n.mood?.toggle||n.mood?.selects.length||n.mood?.numbers.length||n.mood?.buttons?.length)}var vt="adjustable-bed-card",jt={type:vt,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(n,o)=>{let t=n.entities[o];return t?.platform!==P||!t.device_id?null:{config:{type:`custom:${vt}`,device_id:t.device_id}}}};function ge(n){let o=n.customCards??=[],t=o.findIndex(e=>e.type===vt);t===-1?o.push(jt):o[t]=jt}function st(n,o,t=window){let e=t.customElements;e.get(n)||e.define(n,o),e.whenDefined("home-assistant").then(()=>{let i=t.customElements;i!==e&&!i.get(n)&&i.define(n,o)})}typeof window<"u"&&ge(window);var nt=globalThis,rt=nt.ShadowRoot&&(nt.ShadyCSS===void 0||nt.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,yt=Symbol(),Lt=new WeakMap,q=class{constructor(o,t,e){if(this._$cssResult$=!0,e!==yt)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=o,this.t=t}get styleSheet(){let o=this.o,t=this.t;if(rt&&o===void 0){let e=t!==void 0&&t.length===1;e&&(o=Lt.get(t)),o===void 0&&((this.o=o=new CSSStyleSheet).replaceSync(this.cssText),e&&Lt.set(t,o))}return o}toString(){return this.cssText}},Dt=n=>new q(typeof n=="string"?n:n+"",void 0,yt),V=(n,...o)=>{let t=n.length===1?n[0]:o.reduce((e,i,s)=>e+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+n[s+1],n[0]);return new q(t,n,yt)},Nt=(n,o)=>{if(rt)n.adoptedStyleSheets=o.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of o){let e=document.createElement("style"),i=nt.litNonce;i!==void 0&&e.setAttribute("nonce",i),e.textContent=t.cssText,n.appendChild(e)}},xt=rt?n=>n:n=>n instanceof CSSStyleSheet?(o=>{let t="";for(let e of o.cssRules)t+=e.cssText;return Dt(t)})(n):n;var{is:ue,defineProperty:me,getOwnPropertyDescriptor:fe,getOwnPropertyNames:_e,getOwnPropertySymbols:be,getPrototypeOf:ve}=Object,at=globalThis,Ut=at.trustedTypes,ye=Ut?Ut.emptyScript:"",xe=at.reactiveElementPolyfillSupport,Y=(n,o)=>n,J={toAttribute(n,o){switch(o){case Boolean:n=n?ye:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,o){let t=n;switch(o){case Boolean:t=n!==null;break;case Number:t=n===null?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch{t=null}}return t}},ct=(n,o)=>!ue(n,o),Gt={attribute:!0,type:String,converter:J,reflect:!1,useDefault:!1,hasChanged:ct};Symbol.metadata??=Symbol("metadata"),at.litPropertyMetadata??=new WeakMap;var E=class extends HTMLElement{static addInitializer(o){this._$Ei(),(this.l??=[]).push(o)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(o,t=Gt){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(o)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(o,t),!t.noAccessor){let e=Symbol(),i=this.getPropertyDescriptor(o,e,t);i!==void 0&&me(this.prototype,o,i)}}static getPropertyDescriptor(o,t,e){let{get:i,set:s}=fe(this.prototype,o)??{get(){return this[t]},set(r){this[t]=r}};return{get:i,set(r){let a=i?.call(this);s?.call(this,r),this.requestUpdate(o,a,e)},configurable:!0,enumerable:!0}}static getPropertyOptions(o){return this.elementProperties.get(o)??Gt}static _$Ei(){if(this.hasOwnProperty(Y("elementProperties")))return;let o=ve(this);o.finalize(),o.l!==void 0&&(this.l=[...o.l]),this.elementProperties=new Map(o.elementProperties)}static finalize(){if(this.hasOwnProperty(Y("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(Y("properties"))){let t=this.properties,e=[..._e(t),...be(t)];for(let i of e)this.createProperty(i,t[i])}let o=this[Symbol.metadata];if(o!==null){let t=litPropertyMetadata.get(o);if(t!==void 0)for(let[e,i]of t)this.elementProperties.set(e,i)}this._$Eh=new Map;for(let[t,e]of this.elementProperties){let i=this._$Eu(t,e);i!==void 0&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(o){let t=[];if(Array.isArray(o)){let e=new Set(o.flat(1/0).reverse());for(let i of e)t.unshift(xt(i))}else o!==void 0&&t.push(xt(o));return t}static _$Eu(o,t){let e=t.attribute;return e===!1?void 0:typeof e=="string"?e:typeof o=="string"?o.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(o=>this.enableUpdating=o),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(o=>o(this))}addController(o){(this._$EO??=new Set).add(o),this.renderRoot!==void 0&&this.isConnected&&o.hostConnected?.()}removeController(o){this._$EO?.delete(o)}_$E_(){let o=new Map,t=this.constructor.elementProperties;for(let e of t.keys())this.hasOwnProperty(e)&&(o.set(e,this[e]),delete this[e]);o.size>0&&(this._$Ep=o)}createRenderRoot(){let o=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Nt(o,this.constructor.elementStyles),o}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(o=>o.hostConnected?.())}enableUpdating(o){}disconnectedCallback(){this._$EO?.forEach(o=>o.hostDisconnected?.())}attributeChangedCallback(o,t,e){this._$AK(o,e)}_$ET(o,t){let e=this.constructor.elementProperties.get(o),i=this.constructor._$Eu(o,e);if(i!==void 0&&e.reflect===!0){let s=(e.converter?.toAttribute!==void 0?e.converter:J).toAttribute(t,e.type);this._$Em=o,s==null?this.removeAttribute(i):this.setAttribute(i,s),this._$Em=null}}_$AK(o,t){let e=this.constructor,i=e._$Eh.get(o);if(i!==void 0&&this._$Em!==i){let s=e.getPropertyOptions(i),r=typeof s.converter=="function"?{fromAttribute:s.converter}:s.converter?.fromAttribute!==void 0?s.converter:J;this._$Em=i;let a=r.fromAttribute(t,s.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(o,t,e,i=!1,s){if(o!==void 0){let r=this.constructor;if(i===!1&&(s=this[o]),e??=r.getPropertyOptions(o),!((e.hasChanged??ct)(s,t)||e.useDefault&&e.reflect&&s===this._$Ej?.get(o)&&!this.hasAttribute(r._$Eu(o,e))))return;this.C(o,t,e)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(o,t,{useDefault:e,reflect:i,wrapped:s},r){e&&!(this._$Ej??=new Map).has(o)&&(this._$Ej.set(o,r??t??this[o]),s!==!0||r!==void 0)||(this._$AL.has(o)||(this.hasUpdated||e||(t=void 0),this._$AL.set(o,t)),i===!0&&this._$Em!==o&&(this._$Eq??=new Set).add(o))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let o=this.scheduleUpdate();return o!=null&&await o,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,s]of this._$Ep)this[i]=s;this._$Ep=void 0}let e=this.constructor.elementProperties;if(e.size>0)for(let[i,s]of e){let{wrapped:r}=s,a=this[i];r!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,s,a)}}let o=!1,t=this._$AL;try{o=this.shouldUpdate(t),o?(this.willUpdate(t),this._$EO?.forEach(e=>e.hostUpdate?.()),this.update(t)):this._$EM()}catch(e){throw o=!1,this._$EM(),e}o&&this._$AE(t)}willUpdate(o){}_$AE(o){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(o)),this.updated(o)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(o){return!0}update(o){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(o){}firstUpdated(o){}};E.elementStyles=[],E.shadowRootOptions={mode:"open"},E[Y("elementProperties")]=new Map,E[Y("finalized")]=new Map,xe?.({ReactiveElement:E}),(at.reactiveElementVersions??=[]).push("2.1.2");var Ct=globalThis,Ft=n=>n,lt=Ct.trustedTypes,It=lt?lt.createPolicy("lit-html",{createHTML:n=>n}):void 0,Jt="$lit$",A=`lit$${Math.random().toFixed(9).slice(2)}$`,Qt="?"+A,$e=`<${Qt}>`,B=document,Z=()=>B.createComment(""),X=n=>n===null||typeof n!="object"&&typeof n!="function",Tt=Array.isArray,we=n=>Tt(n)||typeof n?.[Symbol.iterator]=="function",$t=`[ \t
\f\r]`,Q=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Kt=/-->/g,Wt=/>/g,M=RegExp(`>|${$t}(?:([^\\s"'>=/]+)(${$t}*=${$t}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),qt=/'/g,Vt=/"/g,Zt=/^(?:script|style|textarea|title)$/i,Pt=n=>(o,...t)=>({_$litType$:n,strings:o,values:t}),p=Pt(1),dt=Pt(2),Ke=Pt(3),z=Symbol.for("lit-noChange"),l=Symbol.for("lit-nothing"),Yt=new WeakMap,R=B.createTreeWalker(B,129);function Xt(n,o){if(!Tt(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return It!==void 0?It.createHTML(o):o}var ke=(n,o)=>{let t=n.length-1,e=[],i,s=o===2?"<svg>":o===3?"<math>":"",r=Q;for(let a=0;a<t;a++){let c=n[a],u,_,f=-1,v=0;for(;v<c.length&&(r.lastIndex=v,_=r.exec(c),_!==null);)v=r.lastIndex,r===Q?_[1]==="!--"?r=Kt:_[1]!==void 0?r=Wt:_[2]!==void 0?(Zt.test(_[2])&&(i=RegExp("</"+_[2],"g")),r=M):_[3]!==void 0&&(r=M):r===M?_[0]===">"?(r=i??Q,f=-1):_[1]===void 0?f=-2:(f=r.lastIndex-_[2].length,u=_[1],r=_[3]===void 0?M:_[3]==='"'?Vt:qt):r===Vt||r===qt?r=M:r===Kt||r===Wt?r=Q:(r=M,i=void 0);let y=r===M&&n[a+1].startsWith("/>")?" ":"";s+=r===Q?c+$e:f>=0?(e.push(u),c.slice(0,f)+Jt+c.slice(f)+A+y):c+A+(f===-2?a:y)}return[Xt(n,s+(n[t]||"<?>")+(o===2?"</svg>":o===3?"</math>":"")),e]},tt=class n{constructor({strings:o,_$litType$:t},e){let i;this.parts=[];let s=0,r=0,a=o.length-1,c=this.parts,[u,_]=ke(o,t);if(this.el=n.createElement(u,e),R.currentNode=this.el.content,t===2||t===3){let f=this.el.content.firstChild;f.replaceWith(...f.childNodes)}for(;(i=R.nextNode())!==null&&c.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let f of i.getAttributeNames())if(f.endsWith(Jt)){let v=_[r++],y=i.getAttribute(f).split(A),m=/([.?@])?(.*)/.exec(v);c.push({type:1,index:s,name:m[2],strings:y,ctor:m[1]==="."?kt:m[1]==="?"?Et:m[1]==="@"?St:G}),i.removeAttribute(f)}else f.startsWith(A)&&(c.push({type:6,index:s}),i.removeAttribute(f));if(Zt.test(i.tagName)){let f=i.textContent.split(A),v=f.length-1;if(v>0){i.textContent=lt?lt.emptyScript:"";for(let y=0;y<v;y++)i.append(f[y],Z()),R.nextNode(),c.push({type:2,index:++s});i.append(f[v],Z())}}}else if(i.nodeType===8)if(i.data===Qt)c.push({type:2,index:s});else{let f=-1;for(;(f=i.data.indexOf(A,f+1))!==-1;)c.push({type:7,index:s}),f+=A.length-1}s++}}static createElement(o,t){let e=B.createElement("template");return e.innerHTML=o,e}};function U(n,o,t=n,e){if(o===z)return o;let i=e!==void 0?t._$Co?.[e]:t._$Cl,s=X(o)?void 0:o._$litDirective$;return i?.constructor!==s&&(i?._$AO?.(!1),s===void 0?i=void 0:(i=new s(n),i._$AT(n,t,e)),e!==void 0?(t._$Co??=[])[e]=i:t._$Cl=i),i!==void 0&&(o=U(n,i._$AS(n,o.values),i,e)),o}var wt=class{constructor(o,t){this._$AV=[],this._$AN=void 0,this._$AD=o,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(o){let{el:{content:t},parts:e}=this._$AD,i=(o?.creationScope??B).importNode(t,!0);R.currentNode=i;let s=R.nextNode(),r=0,a=0,c=e[0];for(;c!==void 0;){if(r===c.index){let u;c.type===2?u=new et(s,s.nextSibling,this,o):c.type===1?u=new c.ctor(s,c.name,c.strings,this,o):c.type===6&&(u=new At(s,this,o)),this._$AV.push(u),c=e[++a]}r!==c?.index&&(s=R.nextNode(),r++)}return R.currentNode=B,i}p(o){let t=0;for(let e of this._$AV)e!==void 0&&(e.strings!==void 0?(e._$AI(o,e,t),t+=e.strings.length-2):e._$AI(o[t])),t++}},et=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(o,t,e,i){this.type=2,this._$AH=l,this._$AN=void 0,this._$AA=o,this._$AB=t,this._$AM=e,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let o=this._$AA.parentNode,t=this._$AM;return t!==void 0&&o?.nodeType===11&&(o=t.parentNode),o}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(o,t=this){o=U(this,o,t),X(o)?o===l||o==null||o===""?(this._$AH!==l&&this._$AR(),this._$AH=l):o!==this._$AH&&o!==z&&this._(o):o._$litType$!==void 0?this.$(o):o.nodeType!==void 0?this.T(o):we(o)?this.k(o):this._(o)}O(o){return this._$AA.parentNode.insertBefore(o,this._$AB)}T(o){this._$AH!==o&&(this._$AR(),this._$AH=this.O(o))}_(o){this._$AH!==l&&X(this._$AH)?this._$AA.nextSibling.data=o:this.T(B.createTextNode(o)),this._$AH=o}$(o){let{values:t,_$litType$:e}=o,i=typeof e=="number"?this._$AC(o):(e.el===void 0&&(e.el=tt.createElement(Xt(e.h,e.h[0]),this.options)),e);if(this._$AH?._$AD===i)this._$AH.p(t);else{let s=new wt(i,this),r=s.u(this.options);s.p(t),this.T(r),this._$AH=s}}_$AC(o){let t=Yt.get(o.strings);return t===void 0&&Yt.set(o.strings,t=new tt(o)),t}k(o){Tt(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,e,i=0;for(let s of o)i===t.length?t.push(e=new n(this.O(Z()),this.O(Z()),this,this.options)):e=t[i],e._$AI(s),i++;i<t.length&&(this._$AR(e&&e._$AB.nextSibling,i),t.length=i)}_$AR(o=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);o!==this._$AB;){let e=Ft(o).nextSibling;Ft(o).remove(),o=e}}setConnected(o){this._$AM===void 0&&(this._$Cv=o,this._$AP?.(o))}},G=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(o,t,e,i,s){this.type=1,this._$AH=l,this._$AN=void 0,this.element=o,this.name=t,this._$AM=i,this.options=s,e.length>2||e[0]!==""||e[1]!==""?(this._$AH=Array(e.length-1).fill(new String),this.strings=e):this._$AH=l}_$AI(o,t=this,e,i){let s=this.strings,r=!1;if(s===void 0)o=U(this,o,t,0),r=!X(o)||o!==this._$AH&&o!==z,r&&(this._$AH=o);else{let a=o,c,u;for(o=s[0],c=0;c<s.length-1;c++)u=U(this,a[e+c],t,c),u===z&&(u=this._$AH[c]),r||=!X(u)||u!==this._$AH[c],u===l?o=l:o!==l&&(o+=(u??"")+s[c+1]),this._$AH[c]=u}r&&!i&&this.j(o)}j(o){o===l?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,o??"")}},kt=class extends G{constructor(){super(...arguments),this.type=3}j(o){this.element[this.name]=o===l?void 0:o}},Et=class extends G{constructor(){super(...arguments),this.type=4}j(o){this.element.toggleAttribute(this.name,!!o&&o!==l)}},St=class extends G{constructor(o,t,e,i,s){super(o,t,e,i,s),this.type=5}_$AI(o,t=this){if((o=U(this,o,t,0)??l)===z)return;let e=this._$AH,i=o===l&&e!==l||o.capture!==e.capture||o.once!==e.once||o.passive!==e.passive,s=o!==l&&(e===l||i);i&&this.element.removeEventListener(this.name,this,e),s&&this.element.addEventListener(this.name,this,o),this._$AH=o}handleEvent(o){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,o):this._$AH.handleEvent(o)}},At=class{constructor(o,t,e){this.element=o,this.type=6,this._$AN=void 0,this._$AM=t,this.options=e}get _$AU(){return this._$AM._$AU}_$AI(o){U(this,o)}};var Ee=Ct.litHtmlPolyfillSupport;Ee?.(tt,et),(Ct.litHtmlVersions??=[]).push("3.3.3");var te=(n,o,t)=>{let e=t?.renderBefore??o,i=e._$litPart$;if(i===void 0){let s=t?.renderBefore??null;e._$litPart$=i=new et(o.insertBefore(Z(),s),s,void 0,t??{})}return i._$AI(n),i};var Mt=globalThis,w=class extends E{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let o=super.createRenderRoot();return this.renderOptions.renderBefore??=o.firstChild,o}update(o){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(o),this._$Do=te(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return z}};w._$litElement$=!0,w.finalized=!0,Mt.litElementHydrateSupport?.({LitElement:w});var Se=Mt.litElementPolyfillSupport;Se?.({LitElement:w});(Mt.litElementVersions??=[]).push("4.2.2");var Ae={attribute:!0,type:String,converter:J,reflect:!1,hasChanged:ct},Ce=(n=Ae,o,t)=>{let{kind:e,metadata:i}=t,s=globalThis.litPropertyMetadata.get(i);if(s===void 0&&globalThis.litPropertyMetadata.set(i,s=new Map),e==="setter"&&((n=Object.create(n)).wrapped=!0),s.set(t.name,n),e==="accessor"){let{name:r}=t;return{set(a){let c=o.get.call(this);o.set.call(this,a),this.requestUpdate(r,c,n,!0,a)},init(a){return a!==void 0&&this.C(r,void 0,n,a),a}}}if(e==="setter"){let{name:r}=t;return function(a){let c=this[r];o.call(this,a),this.requestUpdate(r,c,n,!0,a)}}throw Error("Unsupported decorator location: "+e)};function F(n){return(o,t)=>typeof t=="object"?Ce(n,o,t):((e,i,s)=>{let r=i.hasOwnProperty(s);return i.constructor.createProperty(s,e),r?Object.getOwnPropertyDescriptor(i,s):void 0})(n,o,t)}function C(n){return F({...n,state:!0,attribute:!1})}var H=n=>Math.max(0,Math.min(75,n));function Rt(n,o="theme"){let t=H(n.upper.angle??0),e=H(n.lower.angle??0),i=`rotate(${t} 150 70)`,s=`rotate(${-e} 150 70)`,r=a=>a.angle===void 0?"":`${a.label?`${a.label} `:""}${Math.round(H(a.angle))}\xB0`;return dt`
    <svg
      class="bed-graphic bed-graphic-${o} ${n.moving?"is-moving":""}"
      viewBox="0 -44 300 180"
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
        <g class="bed-panel" transform=${s}>
          <rect class="bed-surface" x="150" y="58" width="108" height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel" transform=${i}>
          <rect class="bed-surface" x="42" y="58" width="108" height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
      </g>

      <text x="86" y="128" text-anchor="middle" class="bed-graphic-label">${r(n.upper)}</text>
      <text x="214" y="128" text-anchor="middle" class="bed-graphic-label">${r(n.lower)}</text>
    </svg>
  `}function Bt(n){let o=H(n.left.upper.angle??0),t=H(n.left.lower.angle??0),e=H(n.right.upper.angle??0),i=H(n.right.lower.angle??0),s=(r,a,c,u)=>dt`
    <g
      class="dual-bed-side dual-bed-side-${r} ${u?"is-moving":""}"
      fill=${`url(#abDual${r==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel"
        transform=${`rotate(${-c} 150 70)`}
      >
        <rect class="dual-bed-surface" x="150" y="58" width="108" height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel"
        transform=${`rotate(${a} 150 70)`}
      >
        <rect class="dual-bed-surface" x="42" y="58" width="108" height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
    </g>
  `;return dt`
    <svg
      class="bed-graphic dual-bed-graphic ${n.left.moving||n.right.moving?"is-moving":""}"
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
      ${s("right",e,i,n.right.moving)}
      ${s("left",o,t,n.left.moving)}
    </svg>
  `}function zt(n){let o=n.find(e=>e.key==="back"||e.key==="head"),t=n.find(e=>e.key==="legs"||e.key==="feet");return o&&t?{upper:o,lower:t}:void 0}function ee(n,o){let t=n.motors.filter(e=>{let i=e.angle??e.position;return o.states[i??""]?.attributes.unit_of_measurement==="\xB0"});return zt(t)!==void 0}var ht=class{constructor(o){this.actions=o;this._key=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0}get heldKey(){return this._key}start(o,t,e,i){this._key===null&&(this._key=o.key,this._cover=o.cover??null,this._stop=i??null,this._pointerId=e,this._repeat(o,t,++this._generation))}async _repeat(o,t,e){for(;e===this._generation;)try{let i=this.actions.pulse(o,t);if(!i)return;await i}catch{return}}endFromPointer(o,t,e){this._pointerId!==null&&t!==this._pointerId||e&&this.end(o)}end(o){let t=this._stop??void 0;if(this.cancel(o)){if(o.cover){this.actions.stopCover(o.cover,t);return}this.actions.stopBed(t)}}cancel(o){return!o||this._key!==o.key?!1:(this._reset(),!0)}stopAll(o){let t=o??this._stop??void 0;this._reset(),this.actions.stopBed(t)}abandon(){let o=this._cover,t=this._stop??void 0,e=this._key!==null;this._reset(),e&&(o?this.actions.stopCover(o,t):this.actions.stopBed(t))}_reset(){this._key=null,this._cover=null,this._stop=null,this._pointerId=null,this._generation++}};var ie={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Actions","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"A \xB7 Glance only","editor.recipe_quick":"B \xB7 Quick actions","editor.recipe_controls":"C \xB7 Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Default / fixed target","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both"};var oe={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Handlinger","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"A \xB7 Kun oversikt","editor.recipe_quick":"B \xB7 Hurtighandlinger","editor.recipe_controls":"C \xB7 Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Standard / fast m\xE5l","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge"};var O={en:ie,nb:oe};function Me(n){let o=(n?.locale?.language||n?.language||"en").toLowerCase(),t=o.split("-")[0];return O[o]?O[o]:O[t]?O[t]:t==="nn"||t==="no"?O.nb:O.en}function g(n,o,t){let i=Me(n)[o]??O.en[o]??o;if(t)for(let[s,r]of Object.entries(t))i=i.replace(`{${s}}`,r);return i}var se=["glance","quick","controls"];function ne(n,o){let t={...n,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:o==="glance"?"names":"angles",show_side_selector:!0,show_motors:o==="controls",show_lighting:!1,show_connection:!1,animate:!0};return o==="glance"?t.compact_actions=[]:delete t.compact_actions,t}function Ht(n,o){return[...o.presets,...o.memory.flatMap(t=>t.goto?[t.goto]:[])].flatMap(t=>{let e=n.entities[t]?.translation_key;return e?[{key:K(e).key,entityId:t}]:[]})}function gt(n,o,t){let e=Ht(n,o);if(t){let r=new Map(e.map(a=>[a.key,a]));return[...new Set(t)].flatMap(a=>{let c=r.get(a);return c?[c]:[]})}let i=e.find(r=>r.key==="preset_flat"),s=e.find(r=>r.key.startsWith("preset_memory_"))??e.find(r=>r!==i);return[i,s].filter(r=>r!==void 0)}function ut(n){return n.stop?[n.stop]:n.motors.flatMap(o=>o.cover?[o.cover]:[])}function mt(n){if(!(!n||!n.startsWith("/")||/^\/[/\\]/.test(n)||/[\\\s]/.test(n)))return n}function ft(n,o){let t=ot(n,o),e=W(n,t);return t&&e.length?[{key:"both",label:g(n,"card.both_sides"),bed:x(n,t)},...e.map(i=>({key:i,label:n.devices[i]?.name_by_user??n.devices[i]?.name??i,bed:x(n,i)}))]:it(n,o)?["both","left","right"].map(i=>({key:i,label:g(n,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:x(n,o,i)})):[{key:"both",label:g(n,"card.both_sides"),bed:x(n,o)}]}var re="4.0.2";function ae(n,o){return{graphic:ee(n,o),motors:n.motors.some(t=>t.cover||t.up||t.down)||!!n.stop||!!n.synchro,firmness:n.firmness.length>0,presets:n.presets.length>0,memory:n.memory.length>0,lighting:N(n.lights)||!!n.lights.state,massage:n.massage.buttons.length>0||n.massage.numbers.length>0||!!n.massage.selects?.length||!!n.massage.timer,utility:n.utility.length>0,climate:n.climate.entities.length>0||n.climate.selects.length>0||n.climate.numbers.length>0,connection:!!(n.connect||n.disconnect)}}var Re="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",Be="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",ze=(n,o)=>n.length===o.length&&n.every((t,e)=>t===o[e]),I=class extends w{constructor(){super(...arguments);this._computeLabel=t=>g(this.hass,`editor.${t.name}`)}setConfig(t){this._config=t}_bed(){let t=this._config?.device_id;if(!this.hass||!t)return;let e=ft(this.hass,t).map(r=>r.bed),i=e[0];if(!i)return;let s=new Map;for(let r of e)for(let a of r.memory){let c=s.get(a.slot);s.set(a.slot,{slot:a.slot,goto:c?.goto??a.goto,save:c?.save??a.save})}return{...i,memory:[...s.values()].sort((r,a)=>r.slot-a.slot)}}_presentKeys(t){let e=this.hass?ft(this.hass,this._config?.device_id).map(i=>i.bed):[t];return D.filter(i=>e.some(s=>ae(s,this.hass)[i]))}_orderedKeys(t){let e=this._presentKeys(t),s=(this._config?.section_order??[]).filter(a=>e.includes(a)),r=e.filter(a=>!s.includes(a));return[...s,...r]}_memorySlots(t){return t?t.memory.map(e=>e.slot):[]}_slotLabel(t){let e=t.goto??t.save,i=e&&this.hass?.states[e]?.attributes.friendly_name||`Memory ${t.slot}`,s=e&&this.hass?.entities[e]?.device_id,r=s?this.hass?.devices[s]:void 0,a=r?.name_by_user||r?.name;return a&&i.startsWith(`${a} `)?i.slice(a.length+1):i}_emit(t){t.type=t.type??"custom:adjustable-bed-card",t.name||delete t.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(t){t.stopPropagation();let e=t.detail.value,i=this._cfg;i.device_id!==e.device_id&&delete i.default_target,i.device_id=e.device_id||void 0,e.name?i.name=e.name:delete i.name,this._emit(i)}_toggleSection(t,e){let i=this._cfg;e?delete i[`show_${t}`]:i[`show_${t}`]=!1,this._emit(i)}_moveSection(t,e,i){let s=this._orderedKeys(t),r=s.indexOf(e),a=r+i;if(r<0||a<0||a>=s.length)return;[s[r],s[a]]=[s[a],s[r]];let c=this._cfg;ze(s,this._presentKeys(t))?delete c.section_order:c.section_order=s,this._emit(c)}_setMemorySave(t){let e=this._cfg;t?delete e.memory_save:e.memory_save=!1,this._emit(e)}_slotChecked(t){let e=this._config?.memory_slots;return!e||!e.length||e.map(Number).includes(t)}_toggleSlot(t,e,i){let s=this._memorySlots(t),r=this._config?.memory_slots,a=r&&r.length?r.map(Number):[...s];i?a.includes(e)||a.push(e):a=a.filter(u=>u!==e),a.sort((u,_)=>u-_);let c=this._cfg;a.length===s.length?delete c.memory_slots:c.memory_slots=a,this._emit(c)}_sectionsGroup(t){let e=this._orderedKeys(t);return e.length?p`
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.sections")}</div>
        ${e.map((i,s)=>{let r=this._config?.[`show_${i}`]!==!1;return p`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${s===0}
                  @click=${()=>this._moveSection(t,i,-1)}
                  title=${g(this.hass,"editor.move_up")}
                  aria-label=${g(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Re}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${s===e.length-1}
                  @click=${()=>this._moveSection(t,i,1)}
                  title=${g(this.hass,"editor.move_down")}
                  aria-label=${g(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Be}></path></svg>
                </button>
              </div>
              <span class="label">${g(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${r}
                @change=${a=>this._toggleSection(i,a.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:l}_memoryGroup(t){if(!(t.memory.length>0&&this._config?.show_memory!==!1))return l;let i=t.memory.some(r=>r.save),s=t.memory.length>1;return!i&&!s?l:p`
      <div class="group">
        <div class="group-title">
          ${g(this.hass,"editor.memory_group")}
        </div>
        ${i?p`<div class="row">
                <span class="label">${g(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                ></ha-switch>
              </div>`:l}
        ${s?p`<div class="sub">
                <div class="sub-label">
                  ${g(this.hass,"editor.memory_slots")}
                </div>
                ${t.memory.map(r=>p`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${a=>this._toggleSlot(t,r.slot,a.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(r)}</span>
                    </label>
                  `)}
              </div>`:l}
      </div>
    `}_setOption(t,e){this._emit({...this._cfg,[t]:e})}_compactToggle(t,e){return p`<div class="row"><span class="label">${g(this.hass,t==="show_connection"?"editor.compact_connection":`editor.${t}`)}</span>
      <ha-switch .checked=${this._config?.[t]??e}
        @change=${i=>this._setOption(t,i.target.checked)}></ha-switch>
    </div>`}_compactGroup(){let t=this._config,e=ft(this.hass,t.device_id),i=e.find(c=>c.key===(t.default_target??"both")),s=e.flatMap(c=>Ht(this.hass,c.bed)).filter((c,u,_)=>_.findIndex(f=>f.key===c.key)===u),r=t.compact_actions??(i?gt(this.hass,i.bed).map(c=>c.key):[]),a=[...r.filter(c=>s.some(u=>u.key===c)),...s.map(c=>c.key).filter(c=>!r.includes(c))];return p`
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        <label class="row"><span class="label">${g(this.hass,"editor.compact_labels")}</span>
          <select .value=${t.compact_labels??"angles"}
            @change=${c=>this._setOption("compact_labels",c.target.value)}>
            ${["angles","names","none"].map(c=>p`
              <option value=${c}>${g(this.hass,`editor.labels_${c}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        <label class="row path-row"><span class="label">${g(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${t.navigation_path??""} placeholder="/dashboard/bed"
            @change=${c=>this._setOption("navigation_path",c.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.compact_controls")}</div>
        ${e.length>1||!i?p`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${g(this.hass,"editor.default_target")}</span>
            <select .value=${t.default_target??"both"}
              @change=${c=>this._setOption("default_target",c.target.value)}>
              ${i?l:p`<option value=${t.default_target}>${g(this.hass,"compact.target_missing")}</option>`}
              ${e.map(c=>p`<option value=${c.key}>${c.label}</option>`)}
            </select>
          </label>`:l}
        ${this._compactToggle("show_motors",!1)}
        ${this._compactToggle("show_lighting",!1)}
        ${this._compactToggle("show_connection",!1)}
        <p class="hint">${g(this.hass,"editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.compact_actions")}</div>
        <p class="hint">${g(this.hass,"editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${()=>this._setOption("compact_actions",void 0)}>${g(this.hass,"editor.actions_auto")}</button>
          <button @click=${()=>this._setOption("compact_actions",[])}>${g(this.hass,"editor.labels_none")}</button>
        </div>
        ${a.map(c=>{let u=s.find(m=>m.key===c),_=r.includes(c),f=r.indexOf(c),v=m=>{let h=[...r];[h[f],h[f+m]]=[h[f+m],h[f]],this._setOption("compact_actions",h)},y=this.hass.states[u.entityId];return p`<div class="row">
            <ha-checkbox .checked=${_} @change=${m=>this._setOption("compact_actions",m.target.checked?[...r,c]:r.filter(h=>h!==c))}></ha-checkbox>
            <span class="label">${y?.attributes.friendly_name??c}</span>
            <button class="icon-btn" ?disabled=${!_||f===0}
              aria-label=${g(this.hass,"editor.move_up")} @click=${()=>v(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!_||f===r.length-1}
              aria-label=${g(this.hass,"editor.move_down")} @click=${()=>v(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return p`<div class="group">
      <label class="row"><span class="label">${g(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${t=>this._setOption("layout",t.target.value)}>
          <option value="full">${g(this.hass,"editor.layout_full")}</option>
          <option value="compact">${g(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${g(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${se.map(t=>p`
        <button @click=${()=>this._emit({...ne(this._config,t)})}>
          ${g(this.hass,`editor.recipe_${t}`)}
        </button>`)}</div>
    </div>`}render(){if(!this.hass||!this._config)return l;let t=this._bed();return p`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():p`
        ${t?this._sectionsGroup(t):l}
        ${t?this._memoryGroup(t):l}
      `}
    `}};I.styles=V`
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
    .label {
      flex: 1;
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
    .check-row {
      display: flex;
      align-items: center;
      gap: 4px;
      cursor: pointer;
    }
  `,$([F({attribute:!1})],I.prototype,"hass",2),$([C()],I.prototype,"_config",2);st("adjustable-bed-card-editor",I);var He=new Set(["back","legs","head","feet"]),k=class extends w{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._watched=[];this._compactStopTargets=new Map;this._hold=new ht({pulse:(t,e)=>{if(t.cover)return this.hass?.callService("cover",e==="up"?"open_cover":"close_cover",{entity_id:t.cover});let i=e==="up"?t.up:t.down;return i?this.hass?.callService("button","press",{entity_id:i}):void 0},stopCover:(t,e)=>this._stopCompactTarget(t,e??t),stopBed:t=>{t&&this._stopCompactTarget(t)}});this._navigate=()=>{let t=mt(this._config?.navigation_path);t&&(this._hold.abandon(),history.pushState(null,"",t),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))}}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(t){return{type:"custom:adjustable-bed-card",device_id:t?Object.values(t.entities).find(i=>i.platform===P)?.device_id:void 0}}setConfig(t){if(!t)throw new Error("Invalid configuration");this._config&&(this._hold.abandon(),this._stopCompact()),(t.device_id!==this._config?.device_id||t.default_target!==this._config?.default_target)&&(this._activePairedPane=t.default_target??"both"),this._config=t}getCardSize(){if(this._config?.layout!=="compact")return 8;let t=this._config;return Math.ceil((24+(t.show_header!==!1?36:0)+(t.show_graphic!==!1?150:0)+(t.compact_labels!=="none"?40:0)+(t.compact_actions?.length===0?0:110)+(t.show_motors===!0?180:0)+(t.show_lighting===!0?70:0)+(t.show_connection===!0?50:0))/50)}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){super.disconnectedCallback(),this._hold.abandon()}shouldUpdate(t){if(t.has("_config")||t.has("_saveModeFor")||t.has("_activePairedPane")||t.has("_synchronizingTo")||t.has("_synchronizationFailed")||!t.has("hass")||!this.hass)return!0;let e=t.get("hass");if(!e||e.entities!==this.hass.entities||e.devices!==this.hass.devices)return!0;for(let i of this._watched)if(e.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return l;if(!this._config.device_id)return this._notice("card.no_device");let t=ot(this.hass,this._config.device_id),e=W(this.hass,t);if(t&&e.length)return this._renderPaired(t,e);if(this._config.device_id&&it(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=x(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),S(i)?this._notice("card.no_entities"):this._config.layout==="compact"?this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:i}],!1):p`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(t,e="theme",i){let s=this._config,r={graphic:()=>s.show_graphic!==!1?i??this._graphic(t,e):l,motors:()=>s.show_motors!==!1?this._motors(t):l,firmness:()=>s.show_firmness!==!1?this._firmness(t):l,presets:()=>s.show_presets!==!1?this._presets(t):l,memory:()=>s.show_memory!==!1?this._memory(t):l,lighting:()=>s.show_lighting!==!1?this._lighting(t):l,massage:()=>s.show_massage!==!1?this._massage(t):l,utility:()=>s.show_utility!==!1?this._utility(t):l,climate:()=>s.show_climate!==!1?this._climate(t):l,connection:()=>s.show_connection!==!1?this._connection(t):l};return this._orderedSections().map(a=>r[a]?.()??l)}_renderPaired(t,e){let i=this.hass,s=x(i,t),r=e.map((a,c)=>({key:a,label:this._deviceLabel(a),bed:x(i,a),graphicTone:c===0?"left":"right",synchronizationTarget:{deviceId:a}}));return this._watched=[s,...r.map(a=>a.bed)].flatMap(a=>this._collectWatched(a)),S(s)&&r.every(a=>S(a.bed))?this._notice("card.no_entities"):this._renderPairedCard(t,[{key:"both",label:g(i,"card.both_sides"),bed:s},...r])}_renderSingleAddressPaired(t){let e=this.hass,i={both:x(e,t,"both"),left:x(e,t,"left"),right:x(e,t,"right")};return this._watched=Object.values(i).flatMap(s=>this._collectWatched(s)),Object.values(i).every(s=>S(s))?this._notice("card.no_entities"):this._renderPairedCard(t,[{key:"both",label:g(e,"card.both_sides"),bed:i.both},{key:"left",label:g(e,"card.left_side"),bed:i.left,graphicTone:"left",synchronizationTarget:{deviceId:t,side:"left"}},{key:"right",label:g(e,"card.right_side"),bed:i.right,graphicTone:"right",synchronizationTarget:{deviceId:t,side:"right"}}])}_renderPairedCard(t,e){if(this._config?.layout==="compact")return this._renderCompact(t,e,!0);let i=e.filter(c=>!S(c.bed)),s=i.find(c=>c.key===this._activePairedPane)??i[0],r=i.filter(c=>c.key!=="both"),a=s.key==="both";return p`
      <ha-card class="paired-card">
        ${this._header(s.bed,t)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(c=>p`
              <button
                class="pane-tab side-${c.graphicTone??"theme"} ${c.key===s.key?"active":""}"
                role="tab"
                aria-selected=${c.key===s.key?"true":"false"}
                @click=${()=>this._selectPairedPane(c.key)}
              >
                ${c.graphicTone?p`<span class="dual-swatch" aria-hidden="true"></span>`:l}
                <span>${c.key==="both"?g(this.hass,"card.both"):c.label}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${s.label}>
          ${this._renderSections(s.bed,s.graphicTone,a?this._pairedOverview(r):void 0)}
          ${a&&this._config?.show_lighting!==!1?this._combinedLighting(s.bed,r):l}
          ${a&&this._config?.show_connection!==!1?this._combinedBluetooth(r):l}
        </div>
      </ha-card>
    `}_renderCompact(t,e,i){let s=this._config,r=e.find(b=>b.key===this._activePairedPane),a=r?.bed,c=a?gt(this.hass,a,s.compact_actions):[],u=s.show_motors===!0&&a?a.motors.filter(b=>b.cover||b.up||b.down||b.position):[],_=c.length>0||u.length>0||s.show_lighting===!0,f=s.compact_actions?.length!==0||s.show_motors===!0||s.show_lighting===!0,v=i?e.filter(b=>b.key!=="both"):e,y=!!a&&ut(a).length>0,m=c.length>0||u.length>0,h=mt(s.navigation_path);return p`
      <ha-card class="compact-card ${f?"":"compact-glance"} ${s.animate===!1?"no-animation":""}">
        ${s.show_header!==!1?p`
          <div class="compact-header">
            <span class="title">${this._title(t)}</span>
            ${h?p`<button class="compact-open" @click=${this._navigate}
              aria-label=${g(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:l}
          </div>`:l}
        ${i&&f?s.show_side_selector!==!1?p`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${e.filter(b=>!S(b.bed)).length}`}
            aria-label=${g(this.hass,"compact.target")}>
            ${e.filter(b=>!S(b.bed)).map(b=>p`
              <button class="pane-tab side-${b.graphicTone??"theme"} ${b.key===r?.key?"active":""}"
                aria-pressed=${b.key===r?.key?"true":"false"}
                title=${b.label}
                @click=${()=>this._selectPairedPane(b.key)}>
                ${b.graphicTone?p`<span class="dual-swatch" aria-hidden="true"></span>`:l}
                <span class="compact-tab-label">${b.key==="both"?g(this.hass,"card.both"):b.label}</span>
              </button>`)}
          </div>`:p`<div class="compact-target">
            ${g(this.hass,"compact.target")}: ${r?.label??g(this.hass,"compact.target_missing")}
          </div>`:l}
        ${s.show_graphic!==!1?this._compactGraphic(v):l}
        ${this._compactReadouts(v)}
        ${!r&&f?p`<div class="hint" role="status">
          ${g(this.hass,"compact.target_missing")}</div>`:l}
        ${u.length?p`<div class="rows compact-motors">
          ${u.map(b=>b.cover||b.up||b.down?this._motorRow(b,a?.stop,!0):this._moreInfoRow(b.position))}
        </div>`:l}
        ${c.length||m||this._compactStopTargets.size?p`
          <div class="tiles compact-actions">
            ${c.map(({entityId:b})=>p`<button class="tile"
              ?disabled=${!y||!this._available(b)}
              @click=${()=>this._compactRecall(b,a)}>
              ${this._icon(b)}<span class="tile-label">${this._name(b)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!y&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(a)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${g(this.hass,"action.stop")}</span>
            </button>
          </div>`:l}
        ${s.show_lighting===!0&&a?p`
          ${this._lighting(a)}
          ${i&&r?.key==="both"?this._combinedLighting(a,v):l}
        `:l}
        ${s.show_connection===!0?p`<div class="compact-connections">
          ${v.map(b=>{let j=this._connectionStatus(b.bed);return j?p`<span>${this._connectionDot(b.bed)}
              ${b.label}: ${g(this.hass,`status.${j}`)}</span>`:l})}
        </div>`:l}
        ${!_&&s.show_graphic===!1&&s.compact_labels==="none"&&s.show_header===!1&&s.show_connection!==!0?p`<div class="hint">${this._title(t)}</div>`:l}
      </ha-card>`}_compactGraphic(t){let e=t.map(u=>this._graphicState(u.bed)),i=e[0],s=e[1],r=e.length>0&&e.every(u=>u!==void 0),a=t.map((u,_)=>`${u.label}: ${e[_]?this._positionSummary(e[_]):g(this.hass,"compact.no_position")}`).join(". "),c=r&&i?s?Bt({left:i,right:s}):Rt({...i,upper:{angle:i.upper.angle},lower:{angle:i.lower.angle}}):p`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${g(this.hass,"compact.no_position")}</span></div>`;return mt(this._config?.navigation_path)?p`<button class="compact-graphic" @click=${this._navigate}
          aria-label="${g(this.hass,"compact.open")}. ${a}">${c}</button>`:p`<div class="compact-graphic" role="img" aria-label=${a}>${c}</div>`}_compactReadouts(t){let e=this._config?.compact_labels??"angles";return e==="none"?l:p`<div class="compact-readouts ${e==="names"?"compact-names":""}">
      ${t.map(i=>p`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span aria-label=${i.label}>${e==="angles"&&t.length>1?[...i.label][0]:i.label}</span>
        </span>
        ${e==="angles"?p`<span class="compact-position"
          title=${i.bed.motors.map(s=>`${this._motorName(s)} ${this._readout(s)??"?"}`).join(" \xB7 ")}
        >${i.bed.motors.filter(s=>s.angle||s.position||s.cover).map(s=>this._readout(s)??"?").join(" / ")||g(this.hass,"compact.no_position")}</span>`:l}
      </div>`)}
    </div>`}_available(t){let e=this._state(t)?.state;return e!==void 0&&e!=="unavailable"}_compactRecall(t,e){this._hold.abandon(),ut(e).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(t),this.requestUpdate()}_stopCompact(t){this._hold.abandon();for(let e of t?ut(t):[])this._compactStopTargets.has(e)||this._compactStopTargets.set(e,Symbol());for(let e of this._compactStopTargets.keys())this._stopCompactTarget(e);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(t,e=t){let i=this._compactStopTargets.get(e),s=t.startsWith("cover.");this.hass?.callService(s?"cover":"button",s?"stop_cover":"press",{entity_id:t}).then(()=>{i!==void 0&&this._compactStopTargets.get(e)===i&&(this._compactStopTargets.delete(e),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(t){this._activePairedPane!==t&&(this._hold.abandon(),this._activePairedPane=t,this._saveModeFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(t){if(!t.connectivity)return;let e=this._state(t.connectivity);return e?.attributes?.state_detail==="connecting"?"connecting":e?.state==="on"?"connected":e?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(t){let e=this._connectionStatus(t);return e?p`<span
      class="connection-dot ${e}"
      title=${g(this.hass,`status.${e}`)}
    ></span>`:l}_pairedOverview(t){let e=t.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(e.length<2)return l;let[i,s]=e;return p`
      <div class="graphic dual-graphic">
        ${Bt({left:i.graphic,right:s.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,s].map(({pane:r,graphic:a},c)=>p`
            <div class="dual-readout side-${c===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${r.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(a)}
              </span>
            </div>
          `)}
      </div>
      ${this._synchronizeSelector(i.pane,s.pane)}
    `}_synchronizeSelector(t,e){if(!t.synchronizationTarget||!e.synchronizationTarget)return l;let i=this._synchronizationPlan(t.bed,e.bed),s=this._synchronizationPlan(e.bed,t.bed);if(i.length===0&&s.length===0)return l;let r=this._synchronizingTo!==void 0;return p`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${g(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${g(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(t,e,"left")}
          >
            ${this._synchronizingTo==="left"?p`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:p`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${g(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||s.length===0}
            @click=${()=>void this._synchronizePositions(t,e,"right")}
          >
            ${this._synchronizingTo==="right"?p`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:p`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?p`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${g(this.hass,"sync.incomplete")}</span>
          </div>`:l}
    `}_synchronizationPlan(t,e){let i=new Map(e.motors.map(a=>[a.key,a])),s=t.motors.filter(a=>He.has(a.key)&&i.has(a.key)&&this._hasPositionFeedback(a)&&this._hasPositionFeedback(i.get(a.key)));if(s.length===0)return[];let r=s.map(a=>({motor:a.key,position:this._angle(a)}));return r.some(a=>a.position===void 0)||s.some(a=>this._angle(i.get(a.key))===void 0)?[]:r}_hasPositionFeedback(t){return t.angle!==void 0||t.position!==void 0}async _synchronizePositions(t,e,i){if(this._synchronizingTo||!this.hass)return;let s=i==="left"?t:e,r=i==="left"?e:t,a=r.synchronizationTarget;if(!a)return;let c=this._synchronizationPlan(s.bed,r.bed);if(c.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(P,"set_positions",{device_id:[a.deviceId],positions:c,...a.side?{side:a.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(t){return(t.upperMotor===t.lowerMotor?[t.upperMotor]:[t.upperMotor,t.lowerMotor]).map(i=>{let s=this._readout(i);return s?`${this._motorName(i)} ${s}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(t,e){if(this._hasLighting(t))return l;let i=e.map(_=>this._mainLight(_.bed)).filter(_=>_!==void 0);if(i.length===0)return l;let s=i.filter(_=>this._state(_)?.state==="on").length,r=s===i.length,a=s>0,c=r?"combined.on":a?"combined.mixed":"combined.off",u=g(this.hass,"combined.lights");return p`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${a?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${u}</span>
          <span class="secondary">${g(this.hass,c)}</span>
        </div>
        <button
          class="toggle ${a?"on":""} ${a&&!r?"mixed":""}"
          role="switch"
          aria-label=${u}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(t){let e=t.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return e.length===0?l:p`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${e.map(({pane:i,entityId:s})=>{let r=this._connectionStatus(i.bed),c=this._state(s)?.attributes.rssi;return p`
            <button
              class="bluetooth-status ${r}"
              @click=${()=>this._moreInfo(s)}
            >
              <ha-icon
                icon=${r==="connected"?"mdi:bluetooth-connect":r==="connecting"?"mdi:bluetooth-transfer":r==="idle"?"mdi:bluetooth":"mdi:bluetooth-off"}
              ></ha-icon>
              <span class="bluetooth-copy">
                <span>${i.label}</span>
                <span class="bluetooth-detail">
                  ${g(this.hass,`status.${r}`)}${typeof c=="number"?` \xB7 ${c} dBm`:""}
                </span>
              </span>
            </button>
          `})}
      </div>
    `}_mainLight(t){return t.lights.light??t.lights.switch}_hasLighting(t){return N(t.lights)}_deviceLabel(t){let e=this.hass?.devices[t];return e?.name_by_user??e?.name??t}_orderedSections(){let t=this._config?.section_order;if(!t?.length)return[...D];let e=new Set(D),i=t.filter(r=>e.has(r)),s=D.filter(r=>!i.includes(r));return[...i,...s]}_header(t,e){let i=this._connectionStatus(t),s={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return p`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(e)}</span>
        ${i===void 0?l:p`
                <button
                  class="conn ${s[i].cls}"
                  @click=${()=>this._moreInfo(t.connectivity)}
                  title=${g(this.hass,s[i].key)}
                >
                  <ha-icon icon=${s[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(t,e="theme"){let i=this._graphicState(t);return i?p`
      <div class="graphic">
        ${Rt(i,e)}
      </div>
    `:l}_graphicState(t){let e=t.motors.filter(c=>{let u=c.angle??c.position;return u!==void 0&&this._state(u)?.attributes.unit_of_measurement==="\xB0"});if(e.length===0||e.some(c=>this._angle(c)===void 0))return;let i=zt(e);if(!i)return;let{upper:s,lower:r}=i,a=t.motors.some(c=>{let u=c.cover?this._state(c.cover)?.state:void 0;return u==="opening"||u==="closing"});return{upperMotor:s,lowerMotor:r,upper:{label:this._motorName(s),angle:this._angle(s)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:a}}_motors(t){let e=t.motors.filter(r=>r.cover||r.up||r.down),i=t.motors.filter(r=>r.position&&!r.cover&&!r.up&&!r.down);if(e.length===0&&i.length===0&&!t.synchro&&!t.stop)return l;let s=e.length>0||i.length>0||!!t.synchro;return p`
      ${s?this._heading("section.position"):l}
      ${t.synchro?this._toggleRow(t.synchro):l}
      ${e.length?p`<div class="rows">
              ${e.map(r=>this._motorRow(r,t.stop))}
            </div>`:l}
      ${i.length?p`<div class="rows">
              ${i.map(r=>this._moreInfoRow(r.position))}
            </div>`:l}
      ${t.stop?p`<button class="stop-all" @click=${()=>this._hold.stopAll(t.stop)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${g(this.hass,"action.stop_all")}</span>
            </button>`:l}
    `}_firmness(t){return t.firmness.length===0?l:p`
      ${this._heading("section.firmness")}
      <div class="rows">${t.firmness.map(e=>this._moreInfoRow(e))}</div>
    `}_motorRow(t,e,i=!1){let s=this._readout(t),r=!!t.cover||!!e,a=p`
      <span>${this._motorName(t)}</span>
      ${s&&!i?p`<span class="readout">${s}</span>`:l}
    `;return p`
      <div class="row">
        ${t.position?p`<button
              class="row-label position-label"
              aria-label=${this._name(t.position)}
              @click=${()=>this._moreInfo(t.position)}
            >${a}</button>`:p`<div class="row-label">${a}</div>`}
        <div class="control-group">
          ${i?this._motorDirection(t,"down",e):l}
          ${this._motorDirection(t,"up",e)}
          ${i?l:p`<button
            class="cg-btn"
            aria-label=${g(this.hass,"action.stop")}
            @click=${()=>this._motorStop(t,e)}
            ?disabled=${!r}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?l:this._motorDirection(t,"down",e)}
        </div>
      </div>
    `}_motorDirection(t,e,i){let s=t.cover??t[e],r=!!t.cover||!!i;return p`
      <button class="cg-btn"
        aria-label=${g(this.hass,`action.${e}`)}
        @pointerdown=${a=>this._startHold(a,t,e,i)}
        @pointerup=${a=>this._endPointerHold(a,t)}
        @pointercancel=${a=>this._endPointerHold(a,t)}
        @keydown=${a=>this._startHold(a,t,e,i)}
        @keyup=${a=>this._endKeyHold(a,t)}
        @blur=${()=>this._endHold(t)}
        @click=${a=>this._activateWithoutPointer(a,t,e,i)}
        ?disabled=${!s||this._config?.layout==="compact"&&(!r||!this._available(s))}
      ><ha-icon icon=${`mdi:chevron-${e}`}></ha-icon></button>`}_presets(t){return t.presets.length===0?l:p`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${t.presets.map(e=>this._tile(e,()=>this._press(e)))}
      </div>
    `}_utility(t){return t.utility.length===0&&!t.utilitySelects?.length?l:p`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${t.utility.map(e=>this._tile(e,()=>e.startsWith("switch.")?this._call("switch","toggle",e):this._press(e)))}
      </div>
      ${t.utilitySelects?.map(e=>this._moreInfoRow(e))}
    `}_memory(t){let e=t.memory,i=this._config?.memory_slots;if(i&&i.length){let c=new Set(i.map(Number));e=e.filter(u=>c.has(u.slot))}if(e.length===0)return l;let s=this._config?.memory_save!==!1&&e.some(c=>c.save),r=e.map(c=>c.save??c.goto??String(c.slot)).join("|"),a=this._saveModeFor===r;return p`
      <div class="section-heading heading-row">
        <span>${g(this.hass,"section.memory")}</span>
        ${s?p`<button
                class="set-btn ${a?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${a?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${g(this.hass,a?"memory.cancel":"memory.set")}</span>
              </button>`:l}
      </div>
      ${a?p`<div class="hint">${g(this.hass,"memory.set_hint")}</div>`:l}
      <div class="tiles">${e.map(c=>this._memoryTile(c,a))}</div>
    `}_memoryTile(t,e){let i=t.goto??t.save;if(e){let r=!!t.save;return p`
        <button
          class="tile ${r?"save-mode":"is-disabled"}"
          ?disabled=${!r}
          @click=${()=>r&&this._saveMemory(t)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(i)}</span>
        </button>
      `}let s=!!t.goto;return p`
      <button
        class="tile ${s?"":"is-disabled"}"
        ?disabled=${!s}
        @click=${()=>t.goto&&this._press(t.goto)}
      >
        ${this._icon(i)}
        <span class="tile-label">${this._name(i)}</span>
      </button>
    `}_lighting(t){let e=t.lights,i=e.light??e.switch;if(!N(e)&&!e.state)return l;let s=i||e.state||e.level||e.timer||e.toggle||e.cycle||e.timerMinutes||e.timerToggle||e.buttons?.length;return p`
      ${this._heading("section.lighting")}
      ${e.mood&&s?this._subheading("lighting.floor"):l}
      ${i?this._toggleRow(i):l}
      ${e.state?this._moreInfoRow(e.state):l}
      ${e.level?this._moreInfoRow(e.level):l}
      ${e.timer?this._moreInfoRow(e.timer):l}
      ${e.timerMinutes?this._moreInfoRow(e.timerMinutes):l}
      ${!e.timerAppliesImmediately&&(e.timerMinutes||e.timerToggle)?p`<div class="hint">${g(this.hass,"lighting.timer_pending")}</div>`:l}
      ${e.toggle||e.cycle||e.timerToggle||e.buttons?.length?p`<div class="tiles">
              ${e.toggle?this._tile(e.toggle,()=>this._press(e.toggle)):l}
              ${e.cycle?this._tile(e.cycle,()=>this._press(e.cycle)):l}
              ${e.timerToggle?this._tile(e.timerToggle,()=>this._press(e.timerToggle)):l}
              ${e.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
            </div>`:l}
      ${e.mood?p`
        ${this._subheading("lighting.mood")}
        ${e.mood.selects.map(r=>this._moreInfoRow(r))}
        ${e.mood.numbers.map(r=>this._moreInfoRow(r))}
        ${e.mood.toggle||e.mood.buttons?.length?p`<div class="tiles">
          ${e.mood.toggle?this._tile(e.mood.toggle,()=>this._press(e.mood.toggle)):l}
          ${e.mood.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
        </div>`:l}
      `:l}
    `}_massage(t){let e=t.massage;return e.buttons.length===0&&e.numbers.length===0&&!e.selects?.length&&!e.timer?l:p`
      ${this._heading("section.massage")}
      ${e.buttons.length?p`<div class="tiles">
              ${e.buttons.map(i=>this._tile(i,()=>this._press(i)))}
            </div>`:l}
      ${e.numbers.map(i=>this._moreInfoRow(i))}
      ${e.selects?.map(i=>this._moreInfoRow(i))}
      ${e.timer?this._moreInfoRow(e.timer):l}
    `}_climate(t){let e=[...t.climate.entities,...t.climate.selects,...t.climate.numbers];return e.length===0?l:p`
      ${this._heading("section.climate")}
      ${e.map(i=>this._moreInfoRow(i))}
    `}_connection(t){return!t.connect&&!t.disconnect?l:p`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${t.connect?this._tile(t.connect,()=>this._press(t.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):l}
        ${t.disconnect?this._tile(t.disconnect,()=>this._press(t.disconnect),{icon:"mdi:bluetooth-off"}):l}
      </div>
    `}_heading(t){return p`<div class="section-heading">${g(this.hass,t)}</div>`}_subheading(t){return p`<div class="lighting-heading">${g(this.hass,t)}</div>`}_tile(t,e,i={}){return p`
      <button class="tile ${i.cls??""}" @click=${e}>
        ${this._icon(t,i.icon)}
        <span class="tile-label">${this._name(t)}</span>
      </button>
    `}_onRowKey(t,e){t.target===t.currentTarget&&(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),e())}_toggleRow(t){let i=this._state(t)?.state==="on",s=this._name(t);return p`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${s}
        @click=${()=>this._moreInfo(t)}
        @keydown=${r=>this._onRowKey(r,()=>this._moreInfo(t))}
      >
        ${this._icon(t)}
        <div class="entity-row-text">
          <span>${s}</span>
          <span class="secondary">${this._stateText(t)}</span>
        </div>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${s}
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(t)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_moreInfoRow(t){let e=this._name(t);return p`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${e}
        @click=${()=>this._moreInfo(t)}
        @keydown=${i=>this._onRowKey(i,()=>this._moreInfo(t))}
      >
        ${this._icon(t)}
        <div class="entity-row-text">
          <span>${e}</span>
        </div>
        <span class="secondary value">${this._stateText(t)}</span>
      </div>
    `}_icon(t,e){let i=this._state(t);return i?p`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:p`<ha-icon class="icon" icon=${e??"mdi:bed"}></ha-icon>`}_notice(t){return p`<ha-card><div class="notice">${g(this.hass,t)}</div></ha-card>`}_state(t){return this.hass?.states[t]}_title(t){return this._config?.name?this._config.name:this._deviceName(t)??g(this.hass,"card.default_name")}_deviceName(t=this._config?.device_id){let e=t?this.hass?.devices[t]:void 0;return e?.name_by_user||e?.name||void 0}_name(t){let e=this._state(t)?.attributes.friendly_name??this.hass?.entities[t]?.name??t,i=this.hass?.entities[t]?.device_id,s=this._deviceName(i);return s&&e.startsWith(s+" ")?e.slice(s.length+1):e}_motorName(t){let e=`motor.${t.key}`,i=g(this.hass,e);return i!==e?i:t.key.split("_").map(s=>s.charAt(0).toUpperCase()+s.slice(1)).join(" ")}_angle(t){let e=t.angle??t.position;if(!e)return;let i=Number.parseFloat(this._state(e)?.state??"");return Number.isFinite(i)?i:void 0}_readout(t){let e=t.angle??t.position;if(e){let i=this._angle(t);if(i===void 0)return;let s=this._state(e)?.attributes.unit_of_measurement,r=t.angle?"\xB0":"%";return`${Math.round(i)}${typeof s=="string"?s:r}`}if(t.cover){let i=this._state(t.cover)?.attributes.current_position;return typeof i=="number"?`${Math.round(i)}%`:void 0}}_stateText(t){let e=this._state(t);if(!e)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(e):e.state}_collectWatched(t){let e=new Set;for(let i of t.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(s=>s&&e.add(s));t.presets.forEach(i=>e.add(i));for(let i of t.memory)[i.goto,i.save].forEach(s=>s&&e.add(s));return[t.stop,t.synchro,t.connect,t.disconnect,t.connectivity,t.lights.light,t.lights.switch,t.lights.state,t.lights.level,t.lights.toggle,t.lights.cycle,t.lights.timer,t.lights.timerMinutes,t.lights.timerToggle,t.lights.mood?.toggle,t.massage.timer].forEach(i=>i&&e.add(i)),t.firmness.forEach(i=>e.add(i)),t.massage.buttons.forEach(i=>e.add(i)),t.lights.buttons?.forEach(i=>e.add(i)),t.massage.numbers.forEach(i=>e.add(i)),t.massage.selects?.forEach(i=>e.add(i)),t.lights.mood?.selects.forEach(i=>e.add(i)),t.lights.mood?.numbers.forEach(i=>e.add(i)),t.lights.mood?.buttons?.forEach(i=>e.add(i)),t.utility.forEach(i=>e.add(i)),t.utilitySelects?.forEach(i=>e.add(i)),t.climate.entities.forEach(i=>e.add(i)),t.climate.selects.forEach(i=>e.add(i)),t.climate.numbers.forEach(i=>e.add(i)),[...e]}_startHold(t,e,i,s){let r=null;if(t instanceof KeyboardEvent){if(t.repeat||t.key!=="Enter"&&t.key!==" ")return;t.preventDefault()}else{if(t.button!==0||!t.isPrimary)return;t.currentTarget.setPointerCapture?.(t.pointerId),t.preventDefault(),r=t.pointerId}this._config?.layout==="compact"&&(s?this._compactStopTargets.set(s,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate()),this._hold.start(e,i,r,s)}_activateWithoutPointer(t,e,i,s){if(t.detail!==0||this._hold.heldKey!==null)return;if(this._config?.layout==="compact"&&(s?this._compactStopTargets.set(s,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate()),e.cover){this._cover(e.cover,i==="up"?"open_cover":"close_cover");return}let r=i==="up"?e.up:e.down;r&&this._press(r)}_endPointerHold(t,e){this._hold.endFromPointer(e,t.pointerId,t.type!=="pointerup"||t.button===0)}_endKeyHold(t,e){t.key!=="Enter"&&t.key!==" "||this._hold.end(e)}_endHold(t){this._hold.end(t)}_motorStop(t,e){if(t.cover){this._hold.cancel(t),this._cover(t.cover,"stop_cover");return}this._hold.stopAll(e)}_toggleSaveMode(t){this._saveModeFor=this._saveModeFor===t?void 0:t}_saveMemory(t){t.save&&this._press(t.save),this._saveModeFor=void 0}_call(t,e,i){this.hass?.callService(t,e,{entity_id:i})?.catch(()=>{})}_press(t){this._call("button","press",t)}_cover(t,e){this._call("cover",e,t)}_toggle(t){this._call("homeassistant","toggle",t)}_setEntities(t,e){this.hass?.callService("homeassistant",e?"turn_on":"turn_off",{entity_id:t})?.catch(()=>{})}_moreInfo(t){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:t},bubbles:!0,composed:!0}))}};k.styles=V`
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
    .compact-graphic { display: block; box-sizing: border-box; width: 100%; padding: 0;
      border: 0; border-radius: 8px; background: none; color: var(--primary-text-color); }
    button.compact-graphic { cursor: pointer; }
    .compact-graphic .bed-graphic { display: block; width: 100%; height: 132px; max-width: 300px; margin: auto; }
    .compact-glance .compact-graphic .bed-graphic { height: 112px; }
    .compact-no-position { min-height: 90px; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 8px; font-size: .75rem;
      color: var(--secondary-text-color); }
    .compact-no-position ha-icon { --mdc-icon-size: 36px; }
    .compact-readouts { display: flex; justify-content: space-between; gap: 8px;
      padding: 0 2px 12px; font-size: 11px; line-height: 17px; color: var(--secondary-text-color); }
    .compact-readouts > div { min-width: 0; display: flex; align-items: center; gap: 5px; }
    .compact-side-name { display: inline-flex; align-items: center; gap: 5px; }
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
    .stop-all:active {
      border-color: var(--error-color);
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
    .bluetooth-status {
      min-width: 0;
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
  `,$([F({attribute:!1})],k.prototype,"hass",2),$([C()],k.prototype,"_config",2),$([C()],k.prototype,"_saveModeFor",2),$([C()],k.prototype,"_activePairedPane",2),$([C()],k.prototype,"_synchronizingTo",2),$([C()],k.prototype,"_synchronizationFailed",2);st("adjustable-bed-card",k);console.info(`%c adjustable-bed-card %c ${re} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{k as AdjustableBedCard};
