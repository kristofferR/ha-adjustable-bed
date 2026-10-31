/* adjustable-bed-card 4.2.4 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var be=Object.defineProperty;var ve=Object.getOwnPropertyDescriptor;var w=(o,s,t,e)=>{for(var i=e>1?void 0:e?ve(s,t):s,n=o.length-1,r;n>=0;n--)(r=o[n])&&(i=(e?r(s,t,i):r(i))||i);return e&&i&&be(s,t,i),i};var B="adjustable_bed";function K(o){for(let s of["left","right","both"]){let t=`_${s}`;if(o.endsWith(t))return{key:o.slice(0,-t.length),side:s}}return{key:o}}var N=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],Ut=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],xt=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_swing","preset_incline","preset_both_up","preset_yoga"],ye={back:"back",foot:"feet",pillow:"pillow"},$e=o=>o.split(".",1)[0],wt=o=>o.translation_key??"";function xe(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[]}}function $(o,s,t){let e=xe();if(!s||!o?.entities)return e;let i=()=>e.lights.mood??={selects:[],numbers:[]},n=o.devices?.[s]?.parent_device_id||Object.values(o.devices??{}).some(g=>g.parent_device_id===s),r=Object.values(o.entities).filter(g=>g.device_id===s&&g.platform===B),a=!!t||!!n&&!r.some(g=>g.translation_key==="ble_connection"),c=new Map,m=g=>{let p=c.get(g);return p||(p={key:g},c.set(g,p)),p},_=new Map,f=new Map,b=g=>{let p=f.get(g);return p||(p={slot:g},f.set(g,p)),p};for(let g of r){if(g.hidden)continue;let p=g.entity_id,fe=$e(p),yt=wt(g);if(!yt)continue;let R=K(yt),Nt=o.states[p]?.attributes.bed_side??o.states[p]?.attributes.side??R.side;if(t&&Nt!==t)continue;let l=a&&R.side===Nt?R.key:yt,S;switch(fe){case"cover":m(l).cover=p;break;case"sensor":l.endsWith("_angle")?m(l.slice(0,-6)).angle=p:l==="logicdata_air_pump_pressure"?e.firmness.push(p):l==="innova_massage_timer"&&(e.massage.timer=p);break;case"number":l.endsWith("_position")?m(l.slice(0,-9)).position=p:!t&&R.side&&R.key.endsWith("_position")?m(`${R.key.slice(0,-9)}_${R.side}`).position=p:l.startsWith("massage_")&&l.endsWith("_intensity")?e.massage.numbers.push(p):l==="light_level"||l==="svane_intensity"||l==="starcode_brightness"||l==="vmatbasic_floor_level"||l==="starcode_abm5_4_light_level"?e.lights.level=p:l==="vmatbasic_floor_minutes"?(e.lights.timerMinutes=p,e.lights.timerAppliesImmediately=!0):l==="vibradorm_app_floor_timer_minutes"?e.lights.timerMinutes=p:(S=l.match(/^richmat_mh_(back|foot|pillow)_angle$/))?m(ye[S[1]]).position=p:l==="richmat_mh_light_timer"?e.lights.timer=p:l==="richmat_mh_light_timer_minutes"?(e.lights.timerMinutes=p,e.lights.timerAppliesImmediately=!0):l==="richmat_mh_head_massage_intensity"||l==="richmat_mh_foot_massage_intensity"?e.massage.numbers.push(p):l==="vibradorm_app_mood_speed"||l==="vmatbasic_mood_speed"||l==="vmatbasic_mood_brightness"?i().numbers.push(p):l==="vibradorm_app_massage_speed"||l==="sleeptracker_wave_minutes"?e.massage.numbers.push(p):/^sleeptracker_(left|right)_level$/.test(l)||l==="fan_level"?e.climate.numbers.push(p):l.startsWith("sleep_number_setting")&&e.firmness.push(p);break;case"button":if(xt.includes(l)||l.startsWith("preset_"))(S=l.match(/^preset_memory_(\d+)$/))?b(Number(S[1])).goto=p:_.set(l,p);else if(S=l.match(/^program_memory_(\d+)$/))b(Number(S[1])).save=p;else if(l==="stop"||l==="stop_both")e.stop=p;else if(l==="connect")e.connect=p;else if(l==="disconnect")e.disconnect=p;else if(l==="sleeptracker_light_toggle")e.lights.toggle=p;else if(l==="sleeptracker_light_off")(e.lights.buttons??=[]).push(p);else if(/^sleeptracker_(massage_|wave_start|wind_down_|local_animation)/.test(l))e.massage.buttons.push(p);else if(l.startsWith("sleeptracker_"))e.utility.push(p);else if(l==="toggle_light")e.lights.toggle=p;else if(l==="light_cycle"||l==="starcode_light_cycle")e.lights.cycle=p;else if(l==="vibradorm_app_mood_toggle"||l==="vmatbasic_mood_toggle")i().toggle=p;else if(l==="vmatbasic_mood_nightlight")(i().buttons??=[]).push(p);else if(l==="vmatbasic_floor_toggle"||l==="vmatbasic_floor_hold")e.lights.toggle=p;else if(l.startsWith("vmatbasic_massage_"))e.massage.buttons.push(p);else if(l==="vibradorm_app_floor_timer_toggle")e.lights.timerToggle=p;else if(l==="remacro_led_brightness_save")(e.lights.buttons??=[]).push(p);else if(l==="starcode_abm5_4_light_plus"||l==="starcode_abm5_4_light_minus"||l==="starcode_abm5_4_light_on"||l==="starcode_abm5_4_light_off")(e.lights.buttons??=[]).push(p);else if(l==="starcode_abm5_4_massage_release")e.massage.buttons.push(p);else if(l.startsWith("starcode_abm5_4_"))e.utility.push(p);else if(l==="okin_app_home")_.set(l,p);else if(l.startsWith("simmons_inclined"))_.set(l,p);else if(l==="simmons_sync_clock"||l==="simmons_refresh_alarms")e.utility.push(p);else if(l==="richmat_mh_massage")e.massage.buttons.push(p);else if(l==="richmat_mh_preset")_.set(`${l}:${p}`,p);else if(l.startsWith("richmat_mh_"))e.utility.push(p);else if(l.startsWith("adjustable_lumbar_wave_")||l==="adjustable_lumbar_massage_on")e.massage.buttons.push(p);else if(l.startsWith("adjustable_lumbar_"))e.utility.push(p);else if(l==="logicdata_app_query_massage")e.massage.buttons.push(p);else if(l.startsWith("logicdata_air_pump_"))e.utility.push(p);else if(l==="ore_comfort_massage_start"||l==="innova_massage_level"||l==="innova_massage_timer_hold")e.massage.buttons.push(p);else if(l==="ore_comfort_program_flat"||l==="ore_comfort_program_zero_g")e.utility.push(p);else if(l==="coolbase_head_massage"||l==="coolbase_foot_massage"||l==="coolbase_massage_mode")e.massage.buttons.push(p);else if(l==="restonic_zzz")e.utility.push(p);else if(l.startsWith("coolbase_"))e.utility.push(p);else if(l==="vibradorm_app_massage_automatic"||l==="vibradorm_app_massage_individual")e.massage.buttons.push(p);else if(l==="sync_positions"||l==="child_lock_toggle"||l==="auxiliary_action"||l==="remote_action"||l==="solace_music_toggle"||l==="solace_music_off"||l==="wake_controller"||l==="reset_defaults"||l==="factory_reset"||l==="vibradorm_app_all_up"||l==="vibradorm_app_all_down"||l==="vibradorm_app_sync"||l==="vibradorm_app_refresh_info"||l==="vmatbasic_all_up"||l==="vmatbasic_all_down"||l==="vmatbasic_refresh_info"||l.startsWith("starcode_save_")||l==="starcode_reset"||l==="starcode_query"||l==="starcode_light_mode")e.utility.push(p);else if(l.startsWith("massage_"))e.massage.buttons.push(p);else if(S=l.match(/^(.+)_(up|down)$/)){let Gt=m(S[1]);Gt[S[2]]=p;let $t=o.states[p]?.attributes.paired_hold_motor;($t==="back"||$t==="legs")&&(Gt.timedMove={deviceId:s,motor:$t})}break;case"switch":l==="under_bed_lights"?e.lights.switch=p:l==="synchro_mode"?e.synchro=p:(l==="linak_automatic_drive"||l==="automatic_light")&&e.utility.push(p);break;case"light":e.lights.light=p;break;case"binary_sensor":l==="ble_connection"?e.connectivity=p:l==="sleeptracker_wind_down_running"?(e.massage.states??=[]).push(p):l==="under_bed_lights"||l==="adjustable_lite_light"||l==="innova_light"||l==="sleeptracker_light_on"?e.lights.state=p:l.startsWith("bed_presence")&&e.presence.push(p);break;case"select":l==="motion_bed_active_module"||l.startsWith("okin_app_")?(e.utilitySelects??=[]).push(p):l==="light_timer"?e.lights.timer=p:l==="remacro_control_side"?e.controlSide=p:l==="starcode_color"||l==="vibradorm_app_mood_palette"||l==="vibradorm_app_mood_effect"||l==="vmatbasic_mood_palette"||l==="vmatbasic_mood_effect"?i().selects.push(p):l==="sleeptracker_wave_frequency"||/^sleeptracker_massage_(head_level|foot_level|pattern_option)$/.test(l)?(e.massage.selects??=[]).push(p):/^sleeptracker_(left|right)_(mode|curve)$/.test(l)?e.climate.selects.push(p):l==="vibradorm_app_massage_wave"?(e.massage.selects??=[]).push(p):l==="richmat_mh_motor_mode"||l==="richmat_mh_snore"?(e.utilitySelects??=[]).push(p):l.startsWith("richmat_mh_waist_")?(e.massage.selects??=[]).push(p):l==="massage_timer"||l==="starcode_abm5_4_massage_timer"||l==="ore_comfort_massage_timer"?e.massage.timer=p:/thermal|footwarming|foundation/.test(l)&&e.climate.selects.push(p);break;case"climate":e.climate.entities.push(p);break}}let v=[...c.keys()],y=[...Ut.filter(g=>c.has(g)),...v.filter(g=>!Ut.includes(g)).sort()];e.motors=y.map(g=>c.get(g)).filter(g=>g.cover||g.up||g.down||g.angle||g.position);let x=[..._.keys()];return e.presets=[...xt.filter(g=>_.has(g)),...x.filter(g=>!xt.includes(g)).sort()].map(g=>_.get(g)),e.memory=[...f.values()].filter(g=>g.goto||g.save).sort((g,p)=>g.slot-p.slot),e}function st(o,s){return!s||!o?.entities?!1:Object.values(o.entities).some(t=>t.device_id===s&&t.platform===B&&(o.states[t.entity_id]?.attributes.bed_side==="both"||K(wt(t)).side==="both"))}function q(o,s){if(!s||!o?.devices)return[];let t=i=>{let n=o.devices[i];return(n?.name_by_user??n?.name??i).toLowerCase()},e=i=>{for(let n of Object.values(o.entities??{})){if(n.device_id!==i||n.platform!=="adjustable_bed")continue;let r=o.states[n.entity_id]?.attributes.bed_side??K(wt(n)).side;if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(o.devices).filter(i=>(i.parent_device_id??i.via_device_id)===s).map(i=>i.id).sort((i,n)=>e(i)-e(n)||t(i).localeCompare(t(n)))}function ot(o,s){if(!s||!o?.devices)return s;let t=o.devices[s]?.parent_device_id??o.devices[s]?.via_device_id;return t&&o.devices[t]&&q(o,t).length?t:s}function T(o){let s=o.lights;return o.motors.length===0&&!o.synchro&&!o.controlSide&&o.firmness.length===0&&o.presets.length===0&&o.memory.length===0&&!o.stop&&!o.connect&&!o.disconnect&&!o.connectivity&&!G(s)&&!s.state&&o.massage.buttons.length===0&&o.massage.numbers.length===0&&!o.massage.selects?.length&&!o.massage.states?.length&&!o.massage.timer&&o.climate.entities.length===0&&o.climate.selects.length===0&&o.climate.numbers.length===0&&o.utility.length===0&&!o.utilitySelects?.length}function G(o){return!!(o.light||o.switch||o.level||o.toggle||o.buttons?.length||o.cycle||o.timer||o.timerMinutes||o.timerToggle||o.mood?.toggle||o.mood?.selects.length||o.mood?.numbers.length||o.mood?.buttons?.length)}var kt="adjustable-bed-card",Ft={type:kt,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(o,s)=>{let t=o.entities[s];return t?.platform!==B||!t.device_id?null:{config:{type:`custom:${kt}`,device_id:t.device_id}}}};function we(o){let s=o.customCards??=[],t=s.findIndex(e=>e.type===kt);t===-1?s.push(Ft):s[t]=Ft}function nt(o,s,t=window){let e=t.customElements;e.get(o)||e.define(o,s),e.whenDefined("home-assistant").then(()=>{let i=t.customElements;i!==e&&!i.get(o)&&i.define(o,s)})}typeof window<"u"&&we(window);var rt=globalThis,at=rt.ShadowRoot&&(rt.ShadyCSS===void 0||rt.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Et=Symbol(),Wt=new WeakMap,V=class{constructor(s,t,e){if(this._$cssResult$=!0,e!==Et)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=t}get styleSheet(){let s=this.o,t=this.t;if(at&&s===void 0){let e=t!==void 0&&t.length===1;e&&(s=Wt.get(t)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),e&&Wt.set(t,s))}return s}toString(){return this.cssText}},It=o=>new V(typeof o=="string"?o:o+"",void 0,Et),X=(o,...s)=>{let t=o.length===1?o[0]:s.reduce((e,i,n)=>e+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+o[n+1],o[0]);return new V(t,o,Et)},Kt=(o,s)=>{if(at)o.adoptedStyleSheets=s.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of s){let e=document.createElement("style"),i=rt.litNonce;i!==void 0&&e.setAttribute("nonce",i),e.textContent=t.cssText,o.appendChild(e)}},St=at?o=>o:o=>o instanceof CSSStyleSheet?(s=>{let t="";for(let e of s.cssRules)t+=e.cssText;return It(t)})(o):o;var{is:ke,defineProperty:Ee,getOwnPropertyDescriptor:Se,getOwnPropertyNames:Ce,getOwnPropertySymbols:Ae,getPrototypeOf:Te}=Object,ct=globalThis,qt=ct.trustedTypes,Me=qt?qt.emptyScript:"",Pe=ct.reactiveElementPolyfillSupport,Y=(o,s)=>o,J={toAttribute(o,s){switch(s){case Boolean:o=o?Me:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,s){let t=o;switch(s){case Boolean:t=o!==null;break;case Number:t=o===null?null:Number(o);break;case Object:case Array:try{t=JSON.parse(o)}catch{t=null}}return t}},lt=(o,s)=>!ke(o,s),Vt={attribute:!0,type:String,converter:J,reflect:!1,useDefault:!1,hasChanged:lt};Symbol.metadata??=Symbol("metadata"),ct.litPropertyMetadata??=new WeakMap;var C=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,t=Vt){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(s,t),!t.noAccessor){let e=Symbol(),i=this.getPropertyDescriptor(s,e,t);i!==void 0&&Ee(this.prototype,s,i)}}static getPropertyDescriptor(s,t,e){let{get:i,set:n}=Se(this.prototype,s)??{get(){return this[t]},set(r){this[t]=r}};return{get:i,set(r){let a=i?.call(this);n?.call(this,r),this.requestUpdate(s,a,e)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??Vt}static _$Ei(){if(this.hasOwnProperty(Y("elementProperties")))return;let s=Te(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(Y("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(Y("properties"))){let t=this.properties,e=[...Ce(t),...Ae(t)];for(let i of e)this.createProperty(i,t[i])}let s=this[Symbol.metadata];if(s!==null){let t=litPropertyMetadata.get(s);if(t!==void 0)for(let[e,i]of t)this.elementProperties.set(e,i)}this._$Eh=new Map;for(let[t,e]of this.elementProperties){let i=this._$Eu(t,e);i!==void 0&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let t=[];if(Array.isArray(s)){let e=new Set(s.flat(1/0).reverse());for(let i of e)t.unshift(St(i))}else s!==void 0&&t.push(St(s));return t}static _$Eu(s,t){let e=t.attribute;return e===!1?void 0:typeof e=="string"?e:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,t=this.constructor.elementProperties;for(let e of t.keys())this.hasOwnProperty(e)&&(s.set(e,this[e]),delete this[e]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Kt(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,t,e){this._$AK(s,e)}_$ET(s,t){let e=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,e);if(i!==void 0&&e.reflect===!0){let n=(e.converter?.toAttribute!==void 0?e.converter:J).toAttribute(t,e.type);this._$Em=s,n==null?this.removeAttribute(i):this.setAttribute(i,n),this._$Em=null}}_$AK(s,t){let e=this.constructor,i=e._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let n=e.getPropertyOptions(i),r=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:J;this._$Em=i;let a=r.fromAttribute(t,n.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(s,t,e,i=!1,n){if(s!==void 0){let r=this.constructor;if(i===!1&&(n=this[s]),e??=r.getPropertyOptions(s),!((e.hasChanged??lt)(n,t)||e.useDefault&&e.reflect&&n===this._$Ej?.get(s)&&!this.hasAttribute(r._$Eu(s,e))))return;this.C(s,t,e)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,t,{useDefault:e,reflect:i,wrapped:n},r){e&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,r??t??this[s]),n!==!0||r!==void 0)||(this._$AL.has(s)||(this.hasUpdated||e||(t=void 0),this._$AL.set(s,t)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,n]of this._$Ep)this[i]=n;this._$Ep=void 0}let e=this.constructor.elementProperties;if(e.size>0)for(let[i,n]of e){let{wrapped:r}=n,a=this[i];r!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,n,a)}}let s=!1,t=this._$AL;try{s=this.shouldUpdate(t),s?(this.willUpdate(t),this._$EO?.forEach(e=>e.hostUpdate?.()),this.update(t)):this._$EM()}catch(e){throw s=!1,this._$EM(),e}s&&this._$AE(t)}willUpdate(s){}_$AE(s){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(s){}firstUpdated(s){}};C.elementStyles=[],C.shadowRootOptions={mode:"open"},C[Y("elementProperties")]=new Map,C[Y("finalized")]=new Map,Pe?.({ReactiveElement:C}),(ct.reactiveElementVersions??=[]).push("2.1.2");var Bt=globalThis,Xt=o=>o,dt=Bt.trustedTypes,Yt=dt?dt.createPolicy("lit-html",{createHTML:o=>o}):void 0,ie="$lit$",M=`lit$${Math.random().toFixed(9).slice(2)}$`,se="?"+M,Re=`<${se}>`,H=document,Q=()=>H.createComment(""),tt=o=>o===null||typeof o!="object"&&typeof o!="function",zt=Array.isArray,Be=o=>zt(o)||typeof o?.[Symbol.iterator]=="function",Ct=`[ \t
\f\r]`,Z=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Jt=/-->/g,Zt=/>/g,z=RegExp(`>|${Ct}(?:([^\\s"'>=/]+)(${Ct}*=${Ct}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),Qt=/'/g,te=/"/g,oe=/^(?:script|style|textarea|title)$/i,Ot=o=>(s,...t)=>({_$litType$:o,strings:s,values:t}),h=Ot(1),D=Ot(2),ei=Ot(3),j=Symbol.for("lit-noChange"),d=Symbol.for("lit-nothing"),ee=new WeakMap,O=H.createTreeWalker(H,129);function ne(o,s){if(!zt(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return Yt!==void 0?Yt.createHTML(s):s}var ze=(o,s)=>{let t=o.length-1,e=[],i,n=s===2?"<svg>":s===3?"<math>":"",r=Z;for(let a=0;a<t;a++){let c=o[a],m,_,f=-1,b=0;for(;b<c.length&&(r.lastIndex=b,_=r.exec(c),_!==null);)b=r.lastIndex,r===Z?_[1]==="!--"?r=Jt:_[1]!==void 0?r=Zt:_[2]!==void 0?(oe.test(_[2])&&(i=RegExp("</"+_[2],"g")),r=z):_[3]!==void 0&&(r=z):r===z?_[0]===">"?(r=i??Z,f=-1):_[1]===void 0?f=-2:(f=r.lastIndex-_[2].length,m=_[1],r=_[3]===void 0?z:_[3]==='"'?te:Qt):r===te||r===Qt?r=z:r===Jt||r===Zt?r=Z:(r=z,i=void 0);let v=r===z&&o[a+1].startsWith("/>")?" ":"";n+=r===Z?c+Re:f>=0?(e.push(m),c.slice(0,f)+ie+c.slice(f)+M+v):c+M+(f===-2?a:v)}return[ne(o,n+(o[t]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),e]},et=class o{constructor({strings:s,_$litType$:t},e){let i;this.parts=[];let n=0,r=0,a=s.length-1,c=this.parts,[m,_]=ze(s,t);if(this.el=o.createElement(m,e),O.currentNode=this.el.content,t===2||t===3){let f=this.el.content.firstChild;f.replaceWith(...f.childNodes)}for(;(i=O.nextNode())!==null&&c.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let f of i.getAttributeNames())if(f.endsWith(ie)){let b=_[r++],v=i.getAttribute(f).split(M),y=/([.?@])?(.*)/.exec(b);c.push({type:1,index:n,name:y[2],strings:v,ctor:y[1]==="."?Tt:y[1]==="?"?Mt:y[1]==="@"?Pt:F}),i.removeAttribute(f)}else f.startsWith(M)&&(c.push({type:6,index:n}),i.removeAttribute(f));if(oe.test(i.tagName)){let f=i.textContent.split(M),b=f.length-1;if(b>0){i.textContent=dt?dt.emptyScript:"";for(let v=0;v<b;v++)i.append(f[v],Q()),O.nextNode(),c.push({type:2,index:++n});i.append(f[b],Q())}}}else if(i.nodeType===8)if(i.data===se)c.push({type:2,index:n});else{let f=-1;for(;(f=i.data.indexOf(M,f+1))!==-1;)c.push({type:7,index:n}),f+=M.length-1}n++}}static createElement(s,t){let e=H.createElement("template");return e.innerHTML=s,e}};function U(o,s,t=o,e){if(s===j)return s;let i=e!==void 0?t._$Co?.[e]:t._$Cl,n=tt(s)?void 0:s._$litDirective$;return i?.constructor!==n&&(i?._$AO?.(!1),n===void 0?i=void 0:(i=new n(o),i._$AT(o,t,e)),e!==void 0?(t._$Co??=[])[e]=i:t._$Cl=i),i!==void 0&&(s=U(o,i._$AS(o,s.values),i,e)),s}var At=class{constructor(s,t){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:t},parts:e}=this._$AD,i=(s?.creationScope??H).importNode(t,!0);O.currentNode=i;let n=O.nextNode(),r=0,a=0,c=e[0];for(;c!==void 0;){if(r===c.index){let m;c.type===2?m=new it(n,n.nextSibling,this,s):c.type===1?m=new c.ctor(n,c.name,c.strings,this,s):c.type===6&&(m=new Rt(n,this,s)),this._$AV.push(m),c=e[++a]}r!==c?.index&&(n=O.nextNode(),r++)}return O.currentNode=H,i}p(s){let t=0;for(let e of this._$AV)e!==void 0&&(e.strings!==void 0?(e._$AI(s,e,t),t+=e.strings.length-2):e._$AI(s[t])),t++}},it=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,t,e,i){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=s,this._$AB=t,this._$AM=e,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,t=this._$AM;return t!==void 0&&s?.nodeType===11&&(s=t.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,t=this){s=U(this,s,t),tt(s)?s===d||s==null||s===""?(this._$AH!==d&&this._$AR(),this._$AH=d):s!==this._$AH&&s!==j&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):Be(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==d&&tt(this._$AH)?this._$AA.nextSibling.data=s:this.T(H.createTextNode(s)),this._$AH=s}$(s){let{values:t,_$litType$:e}=s,i=typeof e=="number"?this._$AC(s):(e.el===void 0&&(e.el=et.createElement(ne(e.h,e.h[0]),this.options)),e);if(this._$AH?._$AD===i)this._$AH.p(t);else{let n=new At(i,this),r=n.u(this.options);n.p(t),this.T(r),this._$AH=n}}_$AC(s){let t=ee.get(s.strings);return t===void 0&&ee.set(s.strings,t=new et(s)),t}k(s){zt(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,e,i=0;for(let n of s)i===t.length?t.push(e=new o(this.O(Q()),this.O(Q()),this,this.options)):e=t[i],e._$AI(n),i++;i<t.length&&(this._$AR(e&&e._$AB.nextSibling,i),t.length=i)}_$AR(s=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);s!==this._$AB;){let e=Xt(s).nextSibling;Xt(s).remove(),s=e}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},F=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,t,e,i,n){this.type=1,this._$AH=d,this._$AN=void 0,this.element=s,this.name=t,this._$AM=i,this.options=n,e.length>2||e[0]!==""||e[1]!==""?(this._$AH=Array(e.length-1).fill(new String),this.strings=e):this._$AH=d}_$AI(s,t=this,e,i){let n=this.strings,r=!1;if(n===void 0)s=U(this,s,t,0),r=!tt(s)||s!==this._$AH&&s!==j,r&&(this._$AH=s);else{let a=s,c,m;for(s=n[0],c=0;c<n.length-1;c++)m=U(this,a[e+c],t,c),m===j&&(m=this._$AH[c]),r||=!tt(m)||m!==this._$AH[c],m===d?s=d:s!==d&&(s+=(m??"")+n[c+1]),this._$AH[c]=m}r&&!i&&this.j(s)}j(s){s===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},Tt=class extends F{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===d?void 0:s}},Mt=class extends F{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==d)}},Pt=class extends F{constructor(s,t,e,i,n){super(s,t,e,i,n),this.type=5}_$AI(s,t=this){if((s=U(this,s,t,0)??d)===j)return;let e=this._$AH,i=s===d&&e!==d||s.capture!==e.capture||s.once!==e.once||s.passive!==e.passive,n=s!==d&&(e===d||i);i&&this.element.removeEventListener(this.name,this,e),n&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},Rt=class{constructor(s,t,e){this.element=s,this.type=6,this._$AN=void 0,this._$AM=t,this.options=e}get _$AU(){return this._$AM._$AU}_$AI(s){U(this,s)}};var Oe=Bt.litHtmlPolyfillSupport;Oe?.(et,it),(Bt.litHtmlVersions??=[]).push("3.3.3");var re=(o,s,t)=>{let e=t?.renderBefore??s,i=e._$litPart$;if(i===void 0){let n=t?.renderBefore??null;e._$litPart$=i=new it(s.insertBefore(Q(),n),n,void 0,t??{})}return i._$AI(o),i};var Ht=globalThis,E=class extends C{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=re(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return j}};E._$litElement$=!0,E.finalized=!0,Ht.litElementHydrateSupport?.({LitElement:E});var He=Ht.litElementPolyfillSupport;He?.({LitElement:E});(Ht.litElementVersions??=[]).push("4.2.2");var je={attribute:!0,type:String,converter:J,reflect:!1,hasChanged:lt},De=(o=je,s,t)=>{let{kind:e,metadata:i}=t,n=globalThis.litPropertyMetadata.get(i);if(n===void 0&&globalThis.litPropertyMetadata.set(i,n=new Map),e==="setter"&&((o=Object.create(o)).wrapped=!0),n.set(t.name,o),e==="accessor"){let{name:r}=t;return{set(a){let c=s.get.call(this);s.set.call(this,a),this.requestUpdate(r,c,o,!0,a)},init(a){return a!==void 0&&this.C(r,void 0,o,a),a}}}if(e==="setter"){let{name:r}=t;return function(a){let c=this[r];s.call(this,a),this.requestUpdate(r,c,o,!0,a)}}throw Error("Unsupported decorator location: "+e)};function W(o){return(s,t)=>typeof t=="object"?De(o,s,t):((e,i,n)=>{let r=i.hasOwnProperty(n);return i.constructor.createProperty(n,e),r?Object.getOwnPropertyDescriptor(i,n):void 0})(o,s,t)}function A(o){return W({...o,state:!0,attribute:!1})}var P=o=>Math.max(0,Math.min(75,o));function ae(o){let s=o.middle?122:150,t=o.middle?178:150,e=P(o.middle?.angle??0)/75*28;return{upperTransform:`rotate(${P(o.upper.angle??0)} ${s} 70)`,lowerTransform:`rotate(${-P(o.lower.angle??0)} ${t} 70)`,upperWidth:s-42,lowerX:t,lowerWidth:258-t,middlePath:`M 125 58 C 137 ${58-e} 163 ${58-e} 175 58 L 175 76 C 163 ${76-e} 137 ${76-e} 125 76 Z`}}function jt(o,s="theme"){let t=ae(o),e=t.upperTransform,i=t.lowerTransform,n=r=>r.angle===void 0?`${r.label?`${r.label} `:""}?`:`${r.label?`${r.label} `:""}${r.readout??`${Math.round(P(r.angle))}\xB0`}`;return D`
    <svg
      class="bed-graphic bed-graphic-${s} ${o.moving?"is-moving":""}"
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
        <g class="bed-panel" transform=${i}>
          <rect class="bed-surface" x=${t.lowerX} y="58" width=${t.lowerWidth} height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel" transform=${e}>
          <rect class="bed-surface" x="42" y="58" width=${t.upperWidth} height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
        ${o.middle?D`<g class="bed-panel bed-lumbar-panel" opacity=${o.middle.angle===void 0?"0.35":"1"}>
          <path class="bed-surface" d=${t.middlePath} />
        </g>`:""}
      </g>

      <text x=${o.middle?80:86} y="128" text-anchor="middle" class="bed-graphic-label">${n(o.upper)}</text>
      ${o.middle?D`<text x="150" y="128" text-anchor="middle" class="bed-graphic-label">${n(o.middle)}</text>`:""}
      <text x=${o.middle?220:214} y="128" text-anchor="middle" class="bed-graphic-label">${n(o.lower)}</text>
    </svg>
  `}function Dt(o){let s=P(o.left.upper.angle??0),t=P(o.left.lower.angle??0),e=P(o.right.upper.angle??0),i=P(o.right.lower.angle??0),n=(r,a,c,m,_)=>{let f=ae({upper:{angle:a},lower:{angle:c},middle:_,moving:m});return D`
    <g
      class="dual-bed-side dual-bed-side-${r} ${m?"is-moving":""}"
      fill=${`url(#abDual${r==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel"
        transform=${f.lowerTransform}
      >
        <rect class="dual-bed-surface" x=${f.lowerX} y="58" width=${f.lowerWidth} height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel"
        transform=${f.upperTransform}
      >
        <rect class="dual-bed-surface" x="42" y="58" width=${f.upperWidth} height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
      ${_?D`<g class="dual-bed-panel bed-lumbar-panel" opacity=${_.angle===void 0?"0.35":"1"}>
        <path class="dual-bed-surface" d=${f.middlePath} />
      </g>`:""}
    </g>
  `};return D`
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
      ${n("right",e,i,o.right.moving,o.right.middle)}
      ${n("left",s,t,o.left.moving,o.left.middle)}
    </svg>
  `}function ht(o){let s=o.find(i=>i.key==="back"||i.key==="head"),t=o.find(i=>i.key==="legs"||i.key==="feet"),e=o.find(i=>i.key==="lumbar");return s&&t?{upper:s,lower:t,...e?{middle:e}:{}}:void 0}function ce(o,s,t=!1){let e=o.motors.filter(i=>{let n=i.angle??i.position,r=s.states[n??""]?.attributes.unit_of_measurement;return r==="\xB0"||t&&r==="%"});return ht(e)!==void 0}function gt(o,s=!1){if(!s)return o;let t=ht(o);if(!t?.middle)return o;let e=[t.upper,t.middle,t.lower];return[...e,...o.filter(i=>!e.includes(i))]}function ut(o,s,t=!1){let e=o.angle??o.position,i=s.states[e??""],n=i?.attributes.unit_of_measurement;if(n!=="\xB0"&&n!=="%"||n==="%"&&!t)return;let r=i.state.trim();if(r==="")return;let a=Number(r);if(!Number.isFinite(a))return;if(n==="\xB0")return{angle:a};let c=Math.max(0,Math.min(100,a));return{angle:c*.75,readout:`${Math.round(c)}%`}}function le(o,s,t){if(s.timedMove)return o?.callService("adjustable_bed","timed_move",{device_id:s.timedMove.deviceId,side:"both",motor:s.timedMove.motor,direction:t,duration_ms:1e3});if(s.cover)return o?.callService("cover",t==="up"?"open_cover":"close_cover",{entity_id:s.cover});let e=t==="up"?s.up:s.down;return e?o?.callService("button","press",{entity_id:e}):void 0}var mt=class{constructor(s){this.actions=s;this._key=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0}get heldKey(){return this._key}start(s,t,e,i){this._key===null&&(this._key=s.key,this._cover=s.cover??null,this._stop=i??null,this._pointerId=e,this._repeat(s,t,++this._generation))}async _repeat(s,t,e){for(;e===this._generation;)try{let i=this.actions.pulse(s,t);if(!i)return;await i}catch{return}}endFromPointer(s,t,e){this._pointerId!==null&&t!==this._pointerId||e&&this.end(s)}end(s){let t=this._stop??void 0;if(this.cancel(s)){if(s.cover){this.actions.stopCover(s.cover,t);return}this.actions.stopBed(t)}}cancel(s){return!s||this._key!==s.key?!1:(this._reset(),!0)}stopAll(s){let t=s??this._stop??void 0;this._reset(),this.actions.stopBed(t)}abandon(){let s=this._cover,t=this._stop??void 0,e=this._key!==null;this._reset(),e&&(s?this.actions.stopCover(s,t):this.actions.stopBed(t))}_reset(){this._key=null,this._cover=null,this._stop=null,this._pointerId=null,this._generation++}};var de={"action.close":"Close","editor.open_dialog":"Open full card in a dialog","editor.show_percentage_graphic":"Draw percentage positions (schematic)","editor.show_lumbar_graphic":"Show a separate lumbar section","section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Actions","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"A \xB7 Glance only","editor.recipe_quick":"B \xB7 Quick actions","editor.recipe_controls":"C \xB7 Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Default / fixed target","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both"};var pe={"action.close":"Lukk","editor.open_dialog":"\xC5pne hele kortet i en dialog","editor.show_percentage_graphic":"Vis prosentposisjoner (skjematisk)","editor.show_lumbar_graphic":"Vis en egen korsryggseksjon","section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Handlinger","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"A \xB7 Kun oversikt","editor.recipe_quick":"B \xB7 Hurtighandlinger","editor.recipe_controls":"C \xB7 Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Standard / fast m\xE5l","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge"};var L={en:de,nb:pe};function Ge(o){let s=(o?.locale?.language||o?.language||"en").toLowerCase(),t=s.split("-")[0];return L[s]?L[s]:L[t]?L[t]:t==="nn"||t==="no"?L.nb:L.en}function u(o,s,t){let i=Ge(o)[s]??L.en[s]??s;if(t)for(let[n,r]of Object.entries(t))i=i.replace(`{${n}}`,r);return i}var he=["glance","quick","controls"];function ge(o){return{...o,show_header:!0,show_graphic:!0,show_motors:!0,show_presets:!0,show_memory:!0,show_lighting:!0,show_massage:!0,show_utility:!0,show_climate:!0,show_firmness:!0,show_connection:!0,...o.dialog_config,type:o.type,device_id:o.device_id,layout:"full",open_dialog:!1,navigation_path:void 0,dialog_config:void 0}}function ue(o,s){let t={...o,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:s==="glance"?"names":"angles",show_side_selector:!0,show_motors:s==="controls",show_lighting:!1,show_connection:!1,animate:!0};return s==="glance"?t.compact_actions=[]:delete t.compact_actions,t}function Lt(o,s){return[...s.presets,...s.memory.flatMap(t=>t.goto?[t.goto]:[])].flatMap(t=>{let e=o.entities[t]?.translation_key;return e?[{key:K(e).key,entityId:t}]:[]})}function _t(o,s,t){let e=Lt(o,s);if(t){let r=new Map(e.map(a=>[a.key,a]));return[...new Set(t)].flatMap(a=>{let c=r.get(a);return c?[c]:[]})}let i=e.find(r=>r.key==="preset_flat"),n=e.find(r=>r.key.startsWith("preset_memory_"))??e.find(r=>r!==i);return[i,n].filter(r=>r!==void 0)}function ft(o){return o.stop?[o.stop]:o.motors.flatMap(s=>s.cover?[s.cover]:[])}function bt(o){if(!(!o||!o.startsWith("/")||/^\/[/\\]/.test(o)||/[\\\s]/.test(o)))return o}function vt(o,s){let t=ot(o,s),e=q(o,t);return t&&e.length?[{key:"both",label:u(o,"card.both_sides"),bed:$(o,t)},...e.map(i=>({key:i,label:o.devices[i]?.name_by_user??o.devices[i]?.name??i,bed:$(o,i)}))]:st(o,s)?["both","left","right"].map(i=>({key:i,label:u(o,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:$(o,s,i)})):[{key:"both",label:u(o,"card.both_sides"),bed:$(o,s)}]}var me="4.2.4";function _e(o,s,t){return{graphic:ce(o,s,t?.show_percentage_graphic===!0),motors:o.motors.some(e=>e.cover||e.up||e.down)||!!o.stop||!!o.synchro,firmness:o.firmness.length>0,presets:o.presets.length>0,memory:o.memory.length>0,lighting:G(o.lights)||!!o.lights.state,massage:o.massage.buttons.length>0||o.massage.numbers.length>0||!!o.massage.states?.length||!!o.massage.selects?.length||!!o.massage.timer,utility:o.utility.length>0,climate:o.climate.entities.length>0||o.climate.selects.length>0||o.climate.numbers.length>0,connection:!!(o.connect||o.disconnect)}}var Ue="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",Fe="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",We=(o,s)=>o.length===s.length&&o.every((t,e)=>t===s[e]),I=class extends E{constructor(){super(...arguments);this._computeLabel=t=>u(this.hass,`editor.${t.name}`)}setConfig(t){this._config=t}_bed(){let t=this._config?.device_id;if(!this.hass||!t)return;let e=vt(this.hass,t).map(r=>r.bed),i=e[0];if(!i)return;let n=new Map;for(let r of e)for(let a of r.memory){let c=n.get(a.slot);n.set(a.slot,{slot:a.slot,goto:c?.goto??a.goto,save:c?.save??a.save})}return{...i,memory:[...n.values()].sort((r,a)=>r.slot-a.slot)}}_presentKeys(t){let e=this.hass?vt(this.hass,this._config?.device_id).map(i=>i.bed):[t];return N.filter(i=>e.some(n=>_e(n,this.hass,this._config)[i]))}_orderedKeys(t){let e=this._presentKeys(t),n=(this._config?.section_order??[]).filter(a=>e.includes(a)),r=e.filter(a=>!n.includes(a));return[...n,...r]}_memorySlots(t){return t?t.memory.map(e=>e.slot):[]}_slotLabel(t){let e=t.goto??t.save,i=e&&this.hass?.states[e]?.attributes.friendly_name||`Memory ${t.slot}`,n=e&&this.hass?.entities[e]?.device_id,r=n?this.hass?.devices[n]:void 0,a=r?.name_by_user||r?.name;return a&&i.startsWith(`${a} `)?i.slice(a.length+1):i}_emit(t){t.type=t.type??"custom:adjustable-bed-card",t.name||delete t.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(t){t.stopPropagation();let e=t.detail.value,i=this._cfg;i.device_id!==e.device_id&&delete i.default_target,i.device_id=e.device_id||void 0,e.name?i.name=e.name:delete i.name,this._emit(i)}_toggleSection(t,e){let i=this._cfg;e?delete i[`show_${t}`]:i[`show_${t}`]=!1,this._emit(i)}_moveSection(t,e,i){let n=this._orderedKeys(t),r=n.indexOf(e),a=r+i;if(r<0||a<0||a>=n.length)return;[n[r],n[a]]=[n[a],n[r]];let c=this._cfg;We(n,this._presentKeys(t))?delete c.section_order:c.section_order=n,this._emit(c)}_setMemorySave(t){let e=this._cfg;t?delete e.memory_save:e.memory_save=!1,this._emit(e)}_slotChecked(t){let e=this._config?.memory_slots;return!e||!e.length||e.map(Number).includes(t)}_toggleSlot(t,e,i){let n=this._memorySlots(t),r=this._config?.memory_slots,a=r&&r.length?r.map(Number):[...n];i?a.includes(e)||a.push(e):a=a.filter(m=>m!==e),a.sort((m,_)=>m-_);let c=this._cfg;a.length===n.length?delete c.memory_slots:c.memory_slots=a,this._emit(c)}_sectionsGroup(t){let e=this._orderedKeys(t);return e.length?h`
      <div class="group">
        <div class="group-title">${u(this.hass,"editor.sections")}</div>
        ${e.map((i,n)=>{let r=this._config?.[`show_${i}`]!==!1;return h`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${n===0}
                  @click=${()=>this._moveSection(t,i,-1)}
                  title=${u(this.hass,"editor.move_up")}
                  aria-label=${u(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Ue}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${n===e.length-1}
                  @click=${()=>this._moveSection(t,i,1)}
                  title=${u(this.hass,"editor.move_down")}
                  aria-label=${u(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Fe}></path></svg>
                </button>
              </div>
              <span class="label">${u(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${r}
                @change=${a=>this._toggleSection(i,a.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:d}_memoryGroup(t){if(!(t.memory.length>0&&this._config?.show_memory!==!1))return d;let i=t.memory.some(r=>r.save),n=t.memory.length>1;return!i&&!n?d:h`
      <div class="group">
        <div class="group-title">
          ${u(this.hass,"editor.memory_group")}
        </div>
        ${i?h`<div class="row">
                <span class="label">${u(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                ></ha-switch>
              </div>`:d}
        ${n?h`<div class="sub">
                <div class="sub-label">
                  ${u(this.hass,"editor.memory_slots")}
                </div>
                ${t.memory.map(r=>h`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${a=>this._toggleSlot(t,r.slot,a.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(r)}</span>
                    </label>
                  `)}
              </div>`:d}
      </div>
    `}_setOption(t,e){this._emit({...this._cfg,[t]:e})}_compactToggle(t,e){return h`<div class="row"><span class="label">${u(this.hass,t==="show_connection"?"editor.compact_connection":`editor.${t}`)}</span>
      <ha-switch .checked=${this._config?.[t]??e}
        @change=${i=>this._setOption(t,i.target.checked)}></ha-switch>
    </div>`}_compactGroup(){let t=this._config,e=vt(this.hass,t.device_id),i=e.find(c=>c.key===(t.default_target??"both")),n=e.flatMap(c=>Lt(this.hass,c.bed)).filter((c,m,_)=>_.findIndex(f=>f.key===c.key)===m),r=t.compact_actions??(i?_t(this.hass,i.bed).map(c=>c.key):[]),a=[...r.filter(c=>n.some(m=>m.key===c)),...n.map(c=>c.key).filter(c=>!r.includes(c))];return h`
      <div class="group">
        <div class="group-title">${u(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        ${this._graphicOptions()}
        <label class="row"><span class="label">${u(this.hass,"editor.compact_labels")}</span>
          <select .value=${t.compact_labels??"angles"}
            @change=${c=>this._setOption("compact_labels",c.target.value)}>
            ${["angles","names","none"].map(c=>h`
              <option value=${c}>${u(this.hass,`editor.labels_${c}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        ${this._compactToggle("open_dialog",!1)}
        <label class="row path-row"><span class="label">${u(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${t.navigation_path??""} placeholder="/dashboard/bed"
            @change=${c=>this._setOption("navigation_path",c.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${u(this.hass,"editor.compact_controls")}</div>
        ${e.length>1||!i?h`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${u(this.hass,"editor.default_target")}</span>
            <select .value=${t.default_target??"both"}
              @change=${c=>this._setOption("default_target",c.target.value)}>
              ${i?d:h`<option value=${t.default_target}>${u(this.hass,"compact.target_missing")}</option>`}
              ${e.map(c=>h`<option value=${c.key}>${c.label}</option>`)}
            </select>
          </label>`:d}
        ${this._compactToggle("show_motors",!1)}
        ${this._compactToggle("show_lighting",!1)}
        ${this._compactToggle("show_connection",!1)}
        <p class="hint">${u(this.hass,"editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${u(this.hass,"editor.compact_actions")}</div>
        <p class="hint">${u(this.hass,"editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${()=>this._setOption("compact_actions",void 0)}>${u(this.hass,"editor.actions_auto")}</button>
          <button @click=${()=>this._setOption("compact_actions",[])}>${u(this.hass,"editor.labels_none")}</button>
        </div>
        ${a.map(c=>{let m=n.find(y=>y.key===c),_=r.includes(c),f=r.indexOf(c),b=y=>{let x=[...r];[x[f],x[f+y]]=[x[f+y],x[f]],this._setOption("compact_actions",x)},v=this.hass.states[m.entityId];return h`<div class="row">
            <ha-checkbox .checked=${_} @change=${y=>this._setOption("compact_actions",y.target.checked?[...r,c]:r.filter(x=>x!==c))}></ha-checkbox>
            <span class="label">${v?.attributes.friendly_name??c}</span>
            <button class="icon-btn" ?disabled=${!_||f===0}
              aria-label=${u(this.hass,"editor.move_up")} @click=${()=>b(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!_||f===r.length-1}
              aria-label=${u(this.hass,"editor.move_down")} @click=${()=>b(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return h`<div class="group">
      <label class="row"><span class="label">${u(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${t=>this._setOption("layout",t.target.value)}>
          <option value="full">${u(this.hass,"editor.layout_full")}</option>
          <option value="compact">${u(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${u(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${he.map(t=>h`
        <button @click=${()=>this._emit({...ue(this._config,t)})}>
          ${u(this.hass,`editor.recipe_${t}`)}
        </button>`)}</div>
    </div>`}_graphicOptions(){return h`
      ${this._compactToggle("show_percentage_graphic",!1)}
      ${this._compactToggle("show_lumbar_graphic",!1)}
    `}render(){if(!this.hass||!this._config)return d;let t=this._bed();return h`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():h`
        ${this._graphicOptions()}
        ${t?this._sectionsGroup(t):d}
        ${t?this._memoryGroup(t):d}
      `}
    `}};I.styles=X`
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
  `,w([W({attribute:!1})],I.prototype,"hass",2),w([A()],I.prototype,"_config",2);nt("adjustable-bed-card-editor",I);var Ie=new Set(["back","legs","head","feet"]),k=class extends E{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._detailsOpen=!1;this._watched=[];this._compactStopTargets=new Map;this._hold=new mt({pulse:(t,e)=>le(this.hass,t,e),stopCover:(t,e)=>this._stopCompactTarget(t,e??t),stopBed:t=>{t&&this._stopCompactTarget(t)}});this._navigate=()=>{let t=bt(this._config?.navigation_path);t&&(this._hold.abandon(),history.pushState(null,"",t),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))};this._openDetails=async()=>{if(!this._config?.open_dialog){this._navigate();return}this._hold.abandon(),this._detailsCard||(this._detailsCard=document.createElement(this.localName),this._detailsCard.setConfig(ge({...this._config,default_target:this._activePairedPane}))),this._detailsCard.hass=this.hass,this._detailsOpen=!0,await this.updateComplete;let t=this.renderRoot.querySelector(".bed-details-dialog");t&&!t.open&&t.showModal()};this._closeDetails=()=>{let t=this.renderRoot.querySelector(".bed-details-dialog");t?.open&&t.close(),this._detailsOpen=!1,this._detailsCard=void 0};this._detailsBackdrop=t=>{if(t.target!==t.currentTarget)return;let e=t.currentTarget.getBoundingClientRect();(t.clientX<e.left||t.clientX>e.right||t.clientY<e.top||t.clientY>e.bottom)&&this._closeDetails()}}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(t){return{type:"custom:adjustable-bed-card",device_id:t?Object.values(t.entities).find(i=>i.platform===B)?.device_id:void 0}}setConfig(t){if(!t)throw new Error("Invalid configuration");this._detailsOpen&&this._closeDetails(),this._config&&(this._hold.abandon(),this._stopCompact()),(t.device_id!==this._config?.device_id||t.default_target!==this._config?.default_target)&&(this._activePairedPane=t.default_target??"both"),this._config=t}getCardSize(){if(this._config?.layout!=="compact")return 8;let t=this._config;return Math.ceil((24+(t.show_header!==!1?36:0)+(t.show_graphic!==!1?150:0)+(t.compact_labels!=="none"?40:0)+(t.compact_actions?.length===0?0:110)+(t.show_motors===!0?180:0)+(t.show_lighting===!0?70:0)+(t.show_connection===!0?50:0))/50)}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){super.disconnectedCallback(),this._hold.abandon(),this._closeDetails()}shouldUpdate(t){if(t.has("_config")||t.has("_detailsOpen")||t.has("_saveModeFor")||t.has("_activePairedPane")||t.has("_synchronizingTo")||t.has("_synchronizationFailed")||!t.has("hass")||!this.hass)return!0;let e=t.get("hass");if(!e||e.entities!==this.hass.entities||e.devices!==this.hass.devices)return!0;for(let i of this._watched)if(e.states[i]!==this.hass.states[i])return!0;return!1}updated(){this._detailsCard&&(this._detailsCard.hass=this.hass)}render(){if(!this.hass||!this._config)return d;if(!this._config.device_id)return this._notice("card.no_device");let t=ot(this.hass,this._config.device_id),e=q(this.hass,t);if(t&&e.length)return this._renderPaired(t,e);if(this._config.device_id&&st(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=$(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),T(i)?this._notice("card.no_entities"):this._config.layout==="compact"?this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:i}],!1):h`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(t,e="theme",i){let n=this._config,r={graphic:()=>n.show_graphic!==!1?i??this._graphic(t,e):d,motors:()=>n.show_motors!==!1?this._motors(t):d,firmness:()=>n.show_firmness!==!1?this._firmness(t):d,presets:()=>n.show_presets!==!1?this._presets(t):d,memory:()=>n.show_memory!==!1?this._memory(t):d,lighting:()=>n.show_lighting!==!1?this._lighting(t):d,massage:()=>n.show_massage!==!1?this._massage(t):d,utility:()=>n.show_utility!==!1?this._utility(t):d,climate:()=>n.show_climate!==!1?this._climate(t):d,connection:()=>n.show_connection!==!1?this._connection(t):d};return this._orderedSections().map(a=>r[a]?.()??d)}_renderPaired(t,e){let i=this.hass,n=$(i,t),r=e.map((a,c)=>({key:a,label:this._deviceLabel(a),bed:$(i,a),graphicTone:c===0?"left":"right",synchronizationTarget:{deviceId:a}}));return this._watched=[n,...r.map(a=>a.bed)].flatMap(a=>this._collectWatched(a)),T(n)&&r.every(a=>T(a.bed))?this._notice("card.no_entities"):this._renderPairedCard(t,[{key:"both",label:u(i,"card.both_sides"),bed:n},...r])}_renderSingleAddressPaired(t){let e=this.hass,i={both:$(e,t,"both"),left:$(e,t,"left"),right:$(e,t,"right")};return this._watched=Object.values(i).flatMap(n=>this._collectWatched(n)),Object.values(i).every(n=>T(n))?this._notice("card.no_entities"):this._renderPairedCard(t,[{key:"both",label:u(e,"card.both_sides"),bed:i.both},{key:"left",label:u(e,"card.left_side"),bed:i.left,graphicTone:"left",synchronizationTarget:{deviceId:t,side:"left"}},{key:"right",label:u(e,"card.right_side"),bed:i.right,graphicTone:"right",synchronizationTarget:{deviceId:t,side:"right"}}])}_renderPairedCard(t,e){if(this._config?.layout==="compact")return this._renderCompact(t,e,!0);let i=e.filter(c=>!T(c.bed)),n=i.find(c=>c.key===this._activePairedPane)??i[0],r=i.filter(c=>c.key!=="both"),a=n.key==="both";return h`
      <ha-card class="paired-card">
        ${this._header(n.bed,t)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(c=>h`
              <button
                class="pane-tab side-${c.graphicTone??"theme"} ${c.key===n.key?"active":""}"
                role="tab"
                aria-selected=${c.key===n.key?"true":"false"}
                @click=${()=>this._selectPairedPane(c.key)}
              >
                ${c.graphicTone?h`<span class="dual-swatch" aria-hidden="true"></span>`:d}
                <span>${c.key==="both"?u(this.hass,"card.both"):c.label}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${n.label}>
          ${this._renderSections(n.bed,n.graphicTone,a?this._pairedOverview(r):void 0)}
          ${a&&this._config?.show_lighting!==!1?this._combinedLighting(n.bed,r):d}
          ${a&&this._config?.show_connection!==!1?this._combinedBluetooth(r):d}
        </div>
      </ha-card>
    `}_renderCompact(t,e,i){let n=this._config,r=e.find(g=>g.key===this._activePairedPane),a=r?.bed,c=a?_t(this.hass,a,n.compact_actions):[],m=n.show_motors===!0&&a?a.motors.filter(g=>g.cover||g.up||g.down||g.position):[],_=c.length>0||m.length>0||n.show_lighting===!0,f=n.compact_actions?.length!==0||n.show_motors===!0||n.show_lighting===!0,b=i?e.filter(g=>g.key!=="both"):e,v=!!a&&ft(a).length>0,y=c.length>0||m.length>0,x=n.open_dialog||bt(n.navigation_path);return h`
      <ha-card class="compact-card ${f?"":"compact-glance"} ${n.animate===!1?"no-animation":""}">
        ${n.show_header!==!1?h`
          <div class="compact-header">
            <span class="title">${this._title(t)}</span>
            ${x?h`<button class="compact-open" @click=${this._openDetails}
              aria-label=${u(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:d}
          </div>`:d}
        ${i&&f?n.show_side_selector!==!1?h`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${e.filter(g=>!T(g.bed)).length}`}
            aria-label=${u(this.hass,"compact.target")}>
            ${e.filter(g=>!T(g.bed)).map(g=>h`
              <button class="pane-tab side-${g.graphicTone??"theme"} ${g.key===r?.key?"active":""}"
                aria-pressed=${g.key===r?.key?"true":"false"}
                title=${g.label}
                @click=${()=>this._selectPairedPane(g.key)}>
                ${g.graphicTone?h`<span class="dual-swatch" aria-hidden="true"></span>`:d}
                <span class="compact-tab-label">${g.key==="both"?u(this.hass,"card.both"):g.label}</span>
              </button>`)}
          </div>`:h`<div class="compact-target">
            ${u(this.hass,"compact.target")}: ${r?.label??u(this.hass,"compact.target_missing")}
          </div>`:d}
        ${n.show_graphic!==!1?this._compactGraphic(b):d}
        ${this._compactReadouts(b)}
        ${!r&&f?h`<div class="hint" role="status">
          ${u(this.hass,"compact.target_missing")}</div>`:d}
        ${m.length?h`<div class="rows compact-motors">
          ${m.map(g=>g.cover||g.up||g.down?this._motorRow(g,a?.stop,!0):this._moreInfoRow(g.position))}
        </div>`:d}
        ${c.length||y||this._compactStopTargets.size?h`
          <div class="tiles compact-actions">
            ${c.map(({entityId:g})=>h`<button class="tile"
              ?disabled=${!v||!this._available(g)}
              @click=${()=>this._compactRecall(g,a)}>
              ${this._icon(g)}<span class="tile-label">${this._name(g)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!v&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(a)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${u(this.hass,"action.stop")}</span>
            </button>
          </div>`:d}
        ${n.show_lighting===!0&&a?h`
          ${this._lighting(a)}
          ${i&&r?.key==="both"?this._combinedLighting(a,b):d}
        `:d}
        ${n.show_connection===!0?i&&r?.key==="both"?this._combinedBluetooth(b):h`<div class="compact-connections">
          ${b.map(g=>{let p=this._connectionStatus(g.bed);return p?h`<span>${this._connectionDot(g.bed)}
              ${g.label}: ${u(this.hass,`status.${p}`)}</span>`:d})}
        </div>`:d}
        ${!_&&n.show_graphic===!1&&n.compact_labels==="none"&&n.show_header===!1&&n.show_connection!==!0?h`<div class="hint">${this._title(t)}</div>`:d}
      </ha-card>
      ${this._detailsOpen?h`<dialog class="bed-details-dialog" aria-label=${this._title(t)}
        @close=${this._closeDetails} @click=${this._detailsBackdrop}>
        <div class="bed-details-heading">
          <strong>${this._title(t)}</strong>
          <button class="bed-details-close" @click=${this._closeDetails}
            aria-label=${u(this.hass,"action.close")}>✕</button>
        </div>
        <div class="bed-details-content">${this._detailsCard}</div>
      </dialog>`:d}`}_compactGraphic(t){let e=t.map(m=>this._graphicState(m.bed)),i=e[0],n=e[1],r=e.length>0&&e.every(m=>m!==void 0),a=t.map((m,_)=>`${m.label}: ${e[_]?this._positionSummary(e[_]):u(this.hass,"compact.no_position")}`).join(". "),c=r&&i?n?Dt({left:i,right:n}):jt({...i,upper:{...i.upper,label:i.middle?i.upper.label:void 0},lower:{...i.lower,label:i.middle?i.lower.label:void 0}}):h`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${u(this.hass,"compact.no_position")}</span></div>`;return this._config?.open_dialog||bt(this._config?.navigation_path)?h`<button class="compact-graphic" @click=${this._openDetails}
          aria-label="${u(this.hass,"compact.open")}. ${a}">${c}</button>`:h`<div class="compact-graphic" role="img" aria-label=${a}>${c}</div>`}_compactReadouts(t){let e=this._config?.compact_labels??"angles";return e==="none"?d:h`<div class="compact-readouts ${e==="names"?"compact-names":""}">
      ${t.map(i=>h`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span aria-label=${i.label}>${e==="angles"&&t.length>1?[...i.label][0]:i.label}</span>
        </span>
        ${e==="angles"?h`<span class="compact-position"
          title=${gt(i.bed.motors,this._config?.show_lumbar_graphic===!0).map(n=>`${this._motorName(n)} ${this._readout(n)??"?"}`).join(" \xB7 ")}
        >${gt(i.bed.motors,this._config?.show_lumbar_graphic===!0).filter(n=>n.angle||n.position||n.cover).map(n=>this._readout(n)??"?").join(" / ")||u(this.hass,"compact.no_position")}</span>`:d}
      </div>`)}
    </div>`}_available(t){let e=this._state(t)?.state;return e!==void 0&&e!=="unavailable"}_compactRecall(t,e){this._hold.abandon(),ft(e).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(t),this.requestUpdate()}_stopCompact(t){this._hold.abandon();for(let e of t?ft(t):[])this._compactStopTargets.has(e)||this._compactStopTargets.set(e,Symbol());for(let e of this._compactStopTargets.keys())this._stopCompactTarget(e);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(t,e=t){let i=this._compactStopTargets.get(e),n=t.startsWith("cover.");this.hass?.callService(n?"cover":"button",n?"stop_cover":"press",{entity_id:t}).then(()=>{i!==void 0&&this._compactStopTargets.get(e)===i&&(this._compactStopTargets.delete(e),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(t){this._activePairedPane!==t&&(this._hold.abandon(),this._activePairedPane=t,this._saveModeFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(t){if(!t.connectivity)return;let e=this._state(t.connectivity);return e?.attributes?.state_detail==="connecting"?"connecting":e?.state==="on"?"connected":e?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(t){let e=this._connectionStatus(t);return e?h`<span
      class="connection-dot ${e}"
      title=${u(this.hass,`status.${e}`)}
    ></span>`:d}_pairedOverview(t){let e=t.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(e.length<2)return d;let[i,n]=e;return h`
      <div class="graphic dual-graphic">
        ${Dt({left:i.graphic,right:n.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,n].map(({pane:r,graphic:a},c)=>h`
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
      ${this._synchronizeSelector(i.pane,n.pane)}
    `}_synchronizeSelector(t,e){if(!t.synchronizationTarget||!e.synchronizationTarget)return d;let i=this._synchronizationPlan(t.bed,e.bed),n=this._synchronizationPlan(e.bed,t.bed);if(i.length===0&&n.length===0)return d;let r=this._synchronizingTo!==void 0;return h`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${u(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${u(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(t,e,"left")}
          >
            ${this._synchronizingTo==="left"?h`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:h`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${u(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||n.length===0}
            @click=${()=>void this._synchronizePositions(t,e,"right")}
          >
            ${this._synchronizingTo==="right"?h`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:h`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?h`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${u(this.hass,"sync.incomplete")}</span>
          </div>`:d}
    `}_synchronizationPlan(t,e){let i=new Map(e.motors.map(a=>[a.key,a])),n=t.motors.filter(a=>Ie.has(a.key)&&i.has(a.key)&&this._hasPositionFeedback(a)&&this._hasPositionFeedback(i.get(a.key)));if(n.length===0)return[];let r=n.map(a=>({motor:a.key,position:this._angle(a)}));return r.some(a=>a.position===void 0)||n.some(a=>this._angle(i.get(a.key))===void 0)?[]:r}_hasPositionFeedback(t){return t.angle!==void 0||t.position!==void 0}async _synchronizePositions(t,e,i){if(this._synchronizingTo||!this.hass)return;let n=i==="left"?t:e,r=i==="left"?e:t,a=r.synchronizationTarget;if(!a)return;let c=this._synchronizationPlan(n.bed,r.bed);if(c.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(B,"set_positions",{device_id:[a.deviceId],positions:c,...a.side?{side:a.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(t){return(t.upperMotor===t.lowerMotor?[t.upperMotor]:[t.upperMotor,...t.middleMotor?[t.middleMotor]:[],t.lowerMotor]).map(i=>{let n=this._readout(i);return n?`${this._motorName(i)} ${n}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(t,e){if(this._hasLighting(t))return d;let i=e.map(_=>this._mainLight(_.bed)).filter(_=>_!==void 0);if(i.length===0)return d;let n=i.filter(_=>this._state(_)?.state==="on").length,r=n===i.length,a=n>0,c=r?"combined.on":a?"combined.mixed":"combined.off",m=u(this.hass,"combined.lights");return h`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${a?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${m}</span>
          <span class="secondary">${u(this.hass,c)}</span>
        </div>
        <button
          class="toggle ${a?"on":""} ${a&&!r?"mixed":""}"
          role="switch"
          aria-label=${m}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(t){let e=t.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return e.length===0?d:h`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${e.map(({pane:i,entityId:n})=>{let r=this._connectionStatus(i.bed),c=this._state(n)?.attributes.rssi;return h`
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
                  ${u(this.hass,`status.${r}`)}${typeof c=="number"?` \xB7 ${c} dBm`:""}
                </span>
              </span>
            </button>
            <div class="tiles">
              ${i.bed.connect?this._tile(i.bed.connect,()=>this._press(i.bed.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):d}
              ${i.bed.disconnect?this._tile(i.bed.disconnect,()=>this._press(i.bed.disconnect),{icon:"mdi:bluetooth-off"}):d}
            </div>
            </div>
          `})}
      </div>
    `}_mainLight(t){return t.lights.light??t.lights.switch}_hasLighting(t){return G(t.lights)}_deviceLabel(t){let e=this.hass?.devices[t];return e?.name_by_user??e?.name??t}_orderedSections(){let t=this._config?.section_order;if(!t?.length)return[...N];let e=new Set(N),i=t.filter(r=>e.has(r)),n=N.filter(r=>!i.includes(r));return[...i,...n]}_header(t,e){let i=this._connectionStatus(t),n={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return h`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(e)}</span>
        ${i===void 0?d:h`
                <button
                  class="conn ${n[i].cls}"
                  @click=${()=>this._moreInfo(t.connectivity)}
                  title=${u(this.hass,n[i].key)}
                >
                  <ha-icon icon=${n[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(t,e="theme"){let i=this._graphicState(t);return i?h`
      <div class="graphic">
        ${jt(i,e)}
      </div>
    `:d}_graphicState(t){if(!this.hass)return;let e=this._config?.show_percentage_graphic===!0,i=t.motors.filter(b=>{let v=b.angle??b.position,y=this._state(v??"")?.attributes.unit_of_measurement;return y==="\xB0"||e&&y==="%"}),n=ht(i);if(!n)return;let{upper:r,lower:a}=n,c=this._config?.show_lumbar_graphic===!0?t.motors.find(b=>b.key==="lumbar"):void 0,m=ut(r,this.hass,e),_=ut(a,this.hass,e);if(!m||!_)return;let f=t.motors.some(b=>{let v=b.cover?this._state(b.cover)?.state:void 0;return v==="opening"||v==="closing"});return{upperMotor:r,lowerMotor:a,middleMotor:c,upper:{label:this._motorName(r),...m},lower:{label:this._motorName(a),..._},middle:c?{label:this._motorName(c),...ut(c,this.hass,e)}:void 0,moving:f}}_motors(t){let e=gt(t.motors,this._config?.show_lumbar_graphic===!0).filter(r=>r.cover||r.up||r.down),i=t.motors.filter(r=>r.position&&!r.cover&&!r.up&&!r.down);if(e.length===0&&i.length===0&&!t.synchro&&!t.controlSide&&!t.stop)return d;let n=e.length>0||i.length>0||!!t.synchro||!!t.controlSide;return h`
      ${n?this._heading("section.position"):d}
      ${t.controlSide?this._moreInfoRow(t.controlSide):d}
      ${t.synchro?this._toggleRow(t.synchro):d}
      ${e.length?h`<div class="rows">
              ${e.map(r=>this._motorRow(r,t.stop))}
            </div>`:d}
      ${i.length?h`<div class="rows">
              ${i.map(r=>this._moreInfoRow(r.position))}
            </div>`:d}
      ${t.stop?h`<button class="stop-all" @click=${()=>this._hold.stopAll(t.stop)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${u(this.hass,"action.stop_all")}</span>
            </button>`:d}
    `}_firmness(t){return t.firmness.length===0?d:h`
      ${this._heading("section.firmness")}
      <div class="rows">${t.firmness.map(e=>this._moreInfoRow(e))}</div>
    `}_motorRow(t,e,i=!1){let n=this._readout(t),r=!!t.cover||!!e,a=h`
      <span>${this._motorName(t)}</span>
      ${n&&!i?h`<span class="readout">${n}</span>`:d}
    `;return h`
      <div class="row">
        ${t.position?h`<button
              class="row-label position-label"
              aria-label=${this._name(t.position)}
              @click=${()=>this._moreInfo(t.position)}
            >${a}</button>`:h`<div class="row-label">${a}</div>`}
        <div class="control-group">
          ${i?this._motorDirection(t,"down",e):d}
          ${this._motorDirection(t,"up",e)}
          ${i?d:h`<button
            class="cg-btn"
            aria-label=${u(this.hass,"action.stop")}
            @click=${()=>this._motorStop(t,e)}
            ?disabled=${!r}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?d:this._motorDirection(t,"down",e)}
        </div>
      </div>
    `}_motorDirection(t,e,i){let n=t.cover??t[e],r=!!t.cover||!!i;return h`
      <button class="cg-btn"
        aria-label=${u(this.hass,`action.${e}`)}
        @pointerdown=${a=>this._startHold(a,t,e,i)}
        @pointerup=${a=>this._endPointerHold(a,t)}
        @pointercancel=${a=>this._endPointerHold(a,t)}
        @keydown=${a=>this._startHold(a,t,e,i)}
        @keyup=${a=>this._endKeyHold(a,t)}
        @blur=${()=>this._endHold(t)}
        @click=${a=>this._activateWithoutPointer(a,t,e,i)}
        ?disabled=${!n||this._config?.layout==="compact"&&(!r||!this._available(n))}
      ><ha-icon icon=${`mdi:chevron-${e}`}></ha-icon></button>`}_presets(t){return t.presets.length===0?d:h`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${t.presets.map(e=>this._tile(e,()=>this._press(e)))}
      </div>
    `}_utility(t){return t.utility.length===0&&!t.utilitySelects?.length?d:h`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${t.utility.map(e=>this._tile(e,()=>e.startsWith("switch.")?this._call("switch","toggle",e):this._press(e)))}
      </div>
      ${t.utilitySelects?.map(e=>this._moreInfoRow(e))}
    `}_memory(t){let e=t.memory,i=this._config?.memory_slots;if(i&&i.length){let c=new Set(i.map(Number));e=e.filter(m=>c.has(m.slot))}if(e.length===0)return d;let n=this._config?.memory_save!==!1&&e.some(c=>c.save),r=e.map(c=>c.save??c.goto??String(c.slot)).join("|"),a=this._saveModeFor===r;return h`
      <div class="section-heading heading-row">
        <span>${u(this.hass,"section.memory")}</span>
        ${n?h`<button
                class="set-btn ${a?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${a?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${u(this.hass,a?"memory.cancel":"memory.set")}</span>
              </button>`:d}
      </div>
      ${a?h`<div class="hint">${u(this.hass,"memory.set_hint")}</div>`:d}
      <div class="tiles">${e.map(c=>this._memoryTile(c,a))}</div>
    `}_memoryTile(t,e){let i=t.goto??t.save;if(e){let r=!!t.save;return h`
        <button
          class="tile ${r?"save-mode":"is-disabled"}"
          ?disabled=${!r}
          @click=${()=>r&&this._saveMemory(t)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(i)}</span>
        </button>
      `}let n=!!t.goto;return h`
      <button
        class="tile ${n?"":"is-disabled"}"
        ?disabled=${!n}
        @click=${()=>t.goto&&this._press(t.goto)}
      >
        ${this._icon(i)}
        <span class="tile-label">${this._name(i)}</span>
      </button>
    `}_lighting(t){let e=t.lights,i=e.light??e.switch;if(!G(e)&&!e.state)return d;let n=i||e.state||e.level||e.timer||e.toggle||e.cycle||e.timerMinutes||e.timerToggle||e.buttons?.length;return h`
      ${this._heading("section.lighting")}
      ${e.mood&&n?this._subheading("lighting.floor"):d}
      ${i?this._toggleRow(i):d}
      ${e.state?this._moreInfoRow(e.state):d}
      ${e.level?this._moreInfoRow(e.level):d}
      ${e.timer?this._moreInfoRow(e.timer):d}
      ${e.timerMinutes?this._moreInfoRow(e.timerMinutes):d}
      ${!e.timerAppliesImmediately&&(e.timerMinutes||e.timerToggle)?h`<div class="hint">${u(this.hass,"lighting.timer_pending")}</div>`:d}
      ${e.toggle||e.cycle||e.timerToggle||e.buttons?.length?h`<div class="tiles">
              ${e.toggle?this._tile(e.toggle,()=>this._press(e.toggle)):d}
              ${e.cycle?this._tile(e.cycle,()=>this._press(e.cycle)):d}
              ${e.timerToggle?this._tile(e.timerToggle,()=>this._press(e.timerToggle)):d}
              ${e.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
            </div>`:d}
      ${e.mood?h`
        ${this._subheading("lighting.mood")}
        ${e.mood.selects.map(r=>this._moreInfoRow(r))}
        ${e.mood.numbers.map(r=>this._moreInfoRow(r))}
        ${e.mood.toggle||e.mood.buttons?.length?h`<div class="tiles">
          ${e.mood.toggle?this._tile(e.mood.toggle,()=>this._press(e.mood.toggle)):d}
          ${e.mood.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
        </div>`:d}
      `:d}
    `}_massage(t){let e=t.massage;return e.buttons.length===0&&e.numbers.length===0&&!e.selects?.length&&!e.states?.length&&!e.timer?d:h`
      ${this._heading("section.massage")}
      ${e.buttons.length?h`<div class="tiles">
              ${e.buttons.map(i=>this._tile(i,()=>this._press(i)))}
            </div>`:d}
      ${e.numbers.map(i=>this._moreInfoRow(i))}
      ${e.selects?.map(i=>this._moreInfoRow(i))}
      ${e.states?.map(i=>this._moreInfoRow(i))}
      ${e.timer?this._moreInfoRow(e.timer):d}
    `}_climate(t){let e=[...t.climate.entities,...t.climate.selects,...t.climate.numbers];return e.length===0?d:h`
      ${this._heading("section.climate")}
      ${e.map(i=>this._moreInfoRow(i))}
    `}_connection(t){return!t.connect&&!t.disconnect?d:h`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${t.connect?this._tile(t.connect,()=>this._press(t.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):d}
        ${t.disconnect?this._tile(t.disconnect,()=>this._press(t.disconnect),{icon:"mdi:bluetooth-off"}):d}
      </div>
    `}_heading(t){return h`<div class="section-heading">${u(this.hass,t)}</div>`}_subheading(t){return h`<div class="lighting-heading">${u(this.hass,t)}</div>`}_tile(t,e,i={}){return h`
      <button class="tile ${i.cls??""}" @click=${e}>
        ${this._icon(t,i.icon)}
        <span class="tile-label">${this._name(t)}</span>
      </button>
    `}_onRowKey(t,e){t.target===t.currentTarget&&(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),e())}_toggleRow(t){let i=this._state(t)?.state==="on",n=this._name(t);return h`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${n}
        @click=${()=>this._moreInfo(t)}
        @keydown=${r=>this._onRowKey(r,()=>this._moreInfo(t))}
      >
        ${this._icon(t)}
        <div class="entity-row-text">
          <span>${n}</span>
          <span class="secondary">${this._stateText(t)}</span>
        </div>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${n}
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(t)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_moreInfoRow(t){let e=this._name(t);return h`
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
    `}_icon(t,e){let i=this._state(t);return i?h`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:h`<ha-icon class="icon" icon=${e??"mdi:bed"}></ha-icon>`}_notice(t){return h`<ha-card><div class="notice">${u(this.hass,t)}</div></ha-card>`}_state(t){return this.hass?.states[t]}_title(t){return this._config?.name?this._config.name:this._deviceName(t)??u(this.hass,"card.default_name")}_deviceName(t=this._config?.device_id){let e=t?this.hass?.devices[t]:void 0;return e?.name_by_user||e?.name||void 0}_name(t){let e=this._state(t)?.attributes.friendly_name??this.hass?.entities[t]?.name??t,i=this.hass?.entities[t]?.device_id,n=this._deviceName(i);return n&&e.startsWith(n+" ")?e.slice(n.length+1):e}_motorName(t){let e=`motor.${t.key}`,i=u(this.hass,e);return i!==e?i:t.key.split("_").map(n=>n.charAt(0).toUpperCase()+n.slice(1)).join(" ")}_angle(t){let e=t.angle??t.position;if(!e)return;let i=Number.parseFloat(this._state(e)?.state??"");return Number.isFinite(i)?i:void 0}_readout(t){let e=t.angle??t.position;if(e){let i=this._angle(t);if(i===void 0)return;let n=this._state(e)?.attributes.unit_of_measurement,r=t.angle?"\xB0":"%";return`${Math.round(i)}${typeof n=="string"?n:r}`}if(t.cover){let i=this._state(t.cover)?.attributes.current_position;return typeof i=="number"?`${Math.round(i)}%`:void 0}}_stateText(t){let e=this._state(t);if(!e)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(e):e.state}_collectWatched(t){let e=new Set;for(let i of t.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(n=>n&&e.add(n));t.presets.forEach(i=>e.add(i));for(let i of t.memory)[i.goto,i.save].forEach(n=>n&&e.add(n));return[t.stop,t.synchro,t.controlSide,t.connect,t.disconnect,t.connectivity,t.lights.light,t.lights.switch,t.lights.state,t.lights.level,t.lights.toggle,t.lights.cycle,t.lights.timer,t.lights.timerMinutes,t.lights.timerToggle,t.lights.mood?.toggle,t.massage.timer].forEach(i=>i&&e.add(i)),t.firmness.forEach(i=>e.add(i)),t.massage.buttons.forEach(i=>e.add(i)),t.lights.buttons?.forEach(i=>e.add(i)),t.massage.numbers.forEach(i=>e.add(i)),t.massage.selects?.forEach(i=>e.add(i)),t.massage.states?.forEach(i=>e.add(i)),t.lights.mood?.selects.forEach(i=>e.add(i)),t.lights.mood?.numbers.forEach(i=>e.add(i)),t.lights.mood?.buttons?.forEach(i=>e.add(i)),t.utility.forEach(i=>e.add(i)),t.utilitySelects?.forEach(i=>e.add(i)),t.climate.entities.forEach(i=>e.add(i)),t.climate.selects.forEach(i=>e.add(i)),t.climate.numbers.forEach(i=>e.add(i)),[...e]}_startHold(t,e,i,n){let r=null;if(t instanceof KeyboardEvent){if(t.repeat||t.key!=="Enter"&&t.key!==" ")return;t.preventDefault()}else{if(t.button!==0||!t.isPrimary)return;t.currentTarget.setPointerCapture?.(t.pointerId),t.preventDefault(),r=t.pointerId}this._config?.layout==="compact"&&(n?this._compactStopTargets.set(n,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate()),this._hold.start(e,i,r,n)}_activateWithoutPointer(t,e,i,n){if(t.detail!==0||this._hold.heldKey!==null)return;if(this._config?.layout==="compact"&&(n?this._compactStopTargets.set(n,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate()),e.cover){this._cover(e.cover,i==="up"?"open_cover":"close_cover");return}let r=i==="up"?e.up:e.down;r&&this._press(r)}_endPointerHold(t,e){this._hold.endFromPointer(e,t.pointerId,t.type!=="pointerup"||t.button===0)}_endKeyHold(t,e){t.key!=="Enter"&&t.key!==" "||this._hold.end(e)}_endHold(t){this._hold.end(t)}_motorStop(t,e){if(t.cover){this._hold.cancel(t),this._cover(t.cover,"stop_cover");return}this._hold.stopAll(e)}_toggleSaveMode(t){this._saveModeFor=this._saveModeFor===t?void 0:t}_saveMemory(t){t.save&&this._press(t.save),this._saveModeFor=void 0}_call(t,e,i){this.hass?.callService(t,e,{entity_id:i})?.catch(()=>{})}_press(t){this._call("button","press",t)}_cover(t,e){this._call("cover",e,t)}_toggle(t){this._call("homeassistant","toggle",t)}_setEntities(t,e){this.hass?.callService("homeassistant",e?"turn_on":"turn_off",{entity_id:t})?.catch(()=>{})}_moreInfo(t){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:t},bubbles:!0,composed:!0}))}};k.styles=X`
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
  `,w([W({attribute:!1})],k.prototype,"hass",2),w([A()],k.prototype,"_config",2),w([A()],k.prototype,"_saveModeFor",2),w([A()],k.prototype,"_activePairedPane",2),w([A()],k.prototype,"_synchronizingTo",2),w([A()],k.prototype,"_synchronizationFailed",2),w([A()],k.prototype,"_detailsOpen",2);nt("adjustable-bed-card",k);console.info(`%c adjustable-bed-card %c ${me} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{k as AdjustableBedCard};
