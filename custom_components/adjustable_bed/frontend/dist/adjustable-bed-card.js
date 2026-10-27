/* adjustable-bed-card 4.2.4 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var $t=Object.defineProperty;var xt=Object.getOwnPropertyDescriptor;var S=(n,s,e,t)=>{for(var i=t>1?void 0:t?xt(s,e):s,o=n.length-1,r;o>=0;o--)(r=n[o])&&(i=(t?r(s,e,i):r(i))||i);return t&&i&&$t(s,e,i),i};var H="adjustable_bed";function Q(n){for(let s of["left","right","both"]){let e=`_${s}`;if(n.endsWith(e))return{key:n.slice(0,-e.length),side:s}}return{key:n}}var K=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],Ie=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],ke=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_swing","preset_incline","preset_both_up","preset_yoga"],wt={back:"back",foot:"feet",pillow:"pillow"},kt=n=>n.split(".",1)[0],Ee=n=>n.translation_key??"";function Et(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[],utilityStates:[]}}function k(n,s,e){let t=Et();if(!s||!n?.entities)return t;let i=()=>t.lights.mood??={selects:[],numbers:[]},o=n.devices?.[s]?.parent_device_id||Object.values(n.devices??{}).some(m=>m.parent_device_id===s),r=Object.values(n.entities).filter(m=>m.device_id===s&&m.platform===H),a=!!e||!!o&&!r.some(m=>m.translation_key==="ble_connection"),l=new Map,g=m=>{let h=l.get(m);return h||(h={key:m},l.set(m,h)),h},v=(m,h,ce,U)=>{let x=g(h);x[ce]=m;let Y=n.states[m]?.attributes,J=Y?.held_control,c=Y?.hold_start_delay_ms,w=Y?.hold_release_delay_ms;typeof J=="string"&&typeof c=="number"&&typeof w=="number"&&U&&(x.deviceId=U,x.holdEntityId=m,x.heldControls={...x.heldControls,[ce]:{control:J,startDelayMs:c,releaseDelayMs:w}});let R=Y?.paired_hold_motor;(R==="back"||R==="legs")&&(x.timedMove={deviceId:s,motor:R})},_=new Map,b=new Map,y=m=>{let h=b.get(m);return h||(h={slot:m},b.set(m,h)),h};for(let m of r){if(m.hidden)continue;let h=m.entity_id,ce=kt(h),U=Ee(m);if(!U)continue;let x=Q(U),J=n.states[h]?.attributes.bed_side??n.states[h]?.attributes.side??x.side;if(e&&J!==e)continue;let c=a&&x.side===J?x.key:U,w;switch(ce){case"cover":{let R=g(c);R.cover=h;let F=n.states[h]?.attributes,Ke=F?.held_control_up,Ge=F?.held_control_down;typeof Ke=="string"&&typeof Ge=="string"&&(m.device_id&&(R.deviceId=m.device_id),R.holdEntityId=h,R.heldControls={up:{control:Ke,startDelayMs:Number(F?.hold_start_delay_ms??0),releaseDelayMs:Number(F?.hold_release_delay_ms??0)},down:{control:Ge,startDelayMs:Number(F?.hold_start_delay_ms??0),releaseDelayMs:Number(F?.hold_release_delay_ms??0)}})}break;case"sensor":c.endsWith("_angle")?g(c.slice(0,-6)).angle=h:c.startsWith("sleepys_app_position_")||c.startsWith("sleepys_app_field_")?t.utilityStates?.push(h):c==="logicdata_air_pump_pressure"?t.firmness.push(h):c==="innova_massage_timer"&&(t.massage.timer=h);break;case"number":c.endsWith("_position")?g(c.slice(0,-9)).position=h:!e&&x.side&&x.key.endsWith("_position")?g(`${x.key.slice(0,-9)}_${x.side}`).position=h:c.startsWith("massage_")&&c.endsWith("_intensity")?t.massage.numbers.push(h):c==="light_level"||c==="svane_intensity"||c==="starcode_brightness"||c==="vmatbasic_floor_level"||c==="starcode_abm5_4_light_level"?t.lights.level=h:c==="vmatbasic_floor_minutes"?(t.lights.timerMinutes=h,t.lights.timerAppliesImmediately=!0):c==="vibradorm_app_floor_timer_minutes"?t.lights.timerMinutes=h:(w=c.match(/^richmat_mh_(back|foot|pillow)_angle$/))?g(wt[w[1]]).position=h:c==="richmat_mh_light_timer"?t.lights.timer=h:c==="richmat_mh_light_timer_minutes"?(t.lights.timerMinutes=h,t.lights.timerAppliesImmediately=!0):c==="richmat_mh_head_massage_intensity"||c==="richmat_mh_foot_massage_intensity"?t.massage.numbers.push(h):c==="vibradorm_app_mood_speed"||c==="vmatbasic_mood_speed"||c==="vmatbasic_mood_brightness"?i().numbers.push(h):c==="vibradorm_app_massage_speed"||c==="sleeptracker_wave_minutes"?t.massage.numbers.push(h):c==="sleepys_app_color_code"?(t.lights.numbers??=[]).push(h):c.startsWith("sleepys_app_target_axis_")?(t.utilityNumbers??=[]).push(h):/^sleeptracker_(left|right)_level$/.test(c)||c==="fan_level"?t.climate.numbers.push(h):c.startsWith("sleep_number_setting")&&t.firmness.push(h);break;case"button":ke.includes(c)||c.startsWith("preset_")||c.startsWith("sleepys_app_preset_")?(w=c.match(/^preset_memory_(\d+)$/))?y(Number(w[1])).goto=h:_.set(c,h):(w=c.match(/^program_memory_(\d+)$/))?y(Number(w[1])).save=h:(w=c.match(/^sleepys_app_memory_(\d+)$/))?y(Number(w[1])).goto=h:c==="stop"||c==="stop_both"?t.stop=h:c==="connect"?t.connect=h:c==="disconnect"?t.disconnect=h:c==="sleeptracker_light_toggle"?t.lights.toggle=h:c==="sleeptracker_light_off"?(t.lights.buttons??=[]).push(h):/^sleeptracker_(massage_|wave_start|wind_down_|local_animation)/.test(c)?t.massage.buttons.push(h):c.startsWith("sleeptracker_")?t.utility.push(h):c.startsWith("sleepys_app_light_")||c.startsWith("sleepys_app_voice_brightness_")||c==="sleepys_app_rgb_action"?(t.lights.buttons??=[]).push(h):c.startsWith("sleepys_app_massage_")?t.massage.buttons.push(h):c==="toggle_light"?t.lights.toggle=h:c==="light_cycle"||c==="starcode_light_cycle"?t.lights.cycle=h:c==="vibradorm_app_mood_toggle"||c==="vmatbasic_mood_toggle"?i().toggle=h:c==="vmatbasic_mood_nightlight"?(i().buttons??=[]).push(h):c==="vmatbasic_floor_toggle"||c==="vmatbasic_floor_hold"?t.lights.toggle=h:c.startsWith("vmatbasic_massage_")?t.massage.buttons.push(h):c==="vibradorm_app_floor_timer_toggle"?t.lights.timerToggle=h:c==="remacro_led_brightness_save"?(t.lights.buttons??=[]).push(h):c==="starcode_abm5_4_light_plus"||c==="starcode_abm5_4_light_minus"||c==="starcode_abm5_4_light_on"||c==="starcode_abm5_4_light_off"?(t.lights.buttons??=[]).push(h):c==="starcode_abm5_4_massage_release"?t.massage.buttons.push(h):c.startsWith("starcode_abm5_4_")?t.utility.push(h):c==="okin_app_home"||c.startsWith("simmons_inclined")?_.set(c,h):c==="simmons_sync_clock"||c==="simmons_refresh_alarms"?t.utility.push(h):c==="richmat_mh_massage"?t.massage.buttons.push(h):c==="richmat_mh_preset"?_.set(`${c}:${h}`,h):c.startsWith("richmat_mh_")?t.utility.push(h):c.startsWith("adjustable_lumbar_wave_")||c==="adjustable_lumbar_massage_on"?t.massage.buttons.push(h):c.startsWith("adjustable_lumbar_")?t.utility.push(h):c==="logicdata_app_query_massage"?t.massage.buttons.push(h):c.startsWith("logicdata_air_pump_")?t.utility.push(h):c==="ore_comfort_massage_start"||c==="innova_massage_level"||c==="innova_massage_timer_hold"?t.massage.buttons.push(h):c==="ore_comfort_program_flat"||c==="ore_comfort_program_zero_g"?t.utility.push(h):c==="coolbase_head_massage"||c==="coolbase_foot_massage"||c==="coolbase_massage_mode"?t.massage.buttons.push(h):c==="restonic_zzz"||c.startsWith("coolbase_")?t.utility.push(h):c==="vibradorm_app_massage_automatic"||c==="vibradorm_app_massage_individual"?t.massage.buttons.push(h):c==="sync_positions"||c==="child_lock_toggle"||c==="auxiliary_action"||c==="remote_action"||c==="solace_music_toggle"||c==="solace_music_off"||c==="wake_controller"||c==="reset_defaults"||c==="factory_reset"||c==="vibradorm_app_all_up"||c==="vibradorm_app_all_down"||c==="vibradorm_app_sync"||c==="vibradorm_app_refresh_info"||c==="vmatbasic_all_up"||c==="vmatbasic_all_down"||c==="vmatbasic_refresh_info"||c.startsWith("starcode_save_")||c==="starcode_reset"||c==="starcode_query"||c==="starcode_light_mode"?t.utility.push(h):c.startsWith("massage_")?t.massage.buttons.push(h):c.startsWith("sleepys_app_")?t.utility.push(h):(w=c.match(/^(.+)_(up|down)$/))&&v(h,w[1],w[2],m.device_id);break;case"switch":c==="under_bed_lights"?t.lights.switch=h:c==="synchro_mode"?t.synchro=h:(c==="linak_automatic_drive"||c==="automatic_light")&&t.utility.push(h);break;case"light":t.lights.light=h;break;case"binary_sensor":c==="ble_connection"?t.connectivity=h:c==="sleeptracker_wind_down_running"?(t.massage.states??=[]).push(h):c==="under_bed_lights"||c==="adjustable_lite_light"||c==="innova_light"||c==="sleeptracker_light_on"?t.lights.state=h:c.startsWith("bed_presence")&&t.presence.push(h);break;case"select":c==="motion_bed_active_module"||c.startsWith("okin_app_")?(t.utilitySelects??=[]).push(h):c==="sleepys_app_massage_timer_code"?(t.massage.selects??=[]).push(h):c==="light_timer"?t.lights.timer=h:c==="remacro_control_side"?t.controlSide=h:c==="starcode_color"||c==="vibradorm_app_mood_palette"||c==="vibradorm_app_mood_effect"||c==="vmatbasic_mood_palette"||c==="vmatbasic_mood_effect"?i().selects.push(h):c==="sleeptracker_wave_frequency"||/^sleeptracker_massage_(head_level|foot_level|pattern_option)$/.test(c)?(t.massage.selects??=[]).push(h):/^sleeptracker_(left|right)_(mode|curve)$/.test(c)?t.climate.selects.push(h):c==="vibradorm_app_massage_wave"?(t.massage.selects??=[]).push(h):c==="richmat_mh_motor_mode"||c==="richmat_mh_snore"?(t.utilitySelects??=[]).push(h):c.startsWith("richmat_mh_waist_")?(t.massage.selects??=[]).push(h):c==="massage_timer"||c==="starcode_abm5_4_massage_timer"||c==="ore_comfort_massage_timer"?t.massage.timer=h:/thermal|footwarming|foundation/.test(c)&&t.climate.selects.push(h);break;case"climate":t.climate.entities.push(h);break}}let $=[...l.keys()],E=[...Ie.filter(m=>l.has(m)),...$.filter(m=>!Ie.includes(m)).sort()];t.motors=E.map(m=>l.get(m)).filter(m=>m.cover||m.up||m.down||m.angle||m.position);let f=[..._.keys()];return t.presets=[...ke.filter(m=>_.has(m)),...f.filter(m=>!ke.includes(m)).sort()].map(m=>_.get(m)),t.memory=[...b.values()].filter(m=>m.goto||m.save).sort((m,h)=>m.slot-h.slot),t}function le(n,s){return!s||!n?.entities?!1:Object.values(n.entities).some(e=>e.device_id===s&&e.platform===H&&(n.states[e.entity_id]?.attributes.bed_side==="both"||Q(Ee(e)).side==="both"))}function Z(n,s){if(!s||!n?.devices)return[];let e=i=>{let o=n.devices[i];return(o?.name_by_user??o?.name??i).toLowerCase()},t=i=>{for(let o of Object.values(n.entities??{})){if(o.device_id!==i||o.platform!=="adjustable_bed")continue;let r=n.states[o.entity_id]?.attributes.bed_side??Q(Ee(o)).side;if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(n.devices).filter(i=>(i.parent_device_id??i.via_device_id)===s).map(i=>i.id).sort((i,o)=>t(i)-t(o)||e(i).localeCompare(e(o)))}function de(n,s){if(!s||!n?.devices)return s;let e=n.devices[s]?.parent_device_id??n.devices[s]?.via_device_id;return e&&n.devices[e]&&Z(n,e).length?e:s}function M(n){let s=n.lights;return n.motors.length===0&&!n.synchro&&!n.controlSide&&n.firmness.length===0&&n.presets.length===0&&n.memory.length===0&&!n.stop&&!n.connect&&!n.disconnect&&!n.connectivity&&!G(s)&&!s.state&&n.massage.buttons.length===0&&n.massage.numbers.length===0&&!n.massage.selects?.length&&!n.massage.states?.length&&!n.massage.timer&&n.climate.entities.length===0&&n.climate.selects.length===0&&n.climate.numbers.length===0&&n.utility.length===0&&!n.utilityNumbers?.length&&!n.utilitySelects?.length&&!n.utilityStates?.length}function G(n){return!!(n.light||n.switch||n.level||n.toggle||n.numbers?.length||n.buttons?.length||n.cycle||n.timer||n.timerMinutes||n.timerToggle||n.mood?.toggle||n.mood?.selects.length||n.mood?.numbers.length||n.mood?.buttons?.length)}var Se="adjustable-bed-card",We={type:Se,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(n,s)=>{let e=n.entities[s];return e?.platform!==H||!e.device_id?null:{config:{type:`custom:${Se}`,device_id:e.device_id}}}};function St(n){let s=n.customCards??=[],e=s.findIndex(t=>t.type===Se);e===-1?s.push(We):s[e]=We}function he(n,s,e=window){let t=e.customElements;t.get(n)||t.define(n,s),t.whenDefined("home-assistant").then(()=>{let i=e.customElements;i!==t&&!i.get(n)&&i.define(n,s)})}typeof window<"u"&&St(window);var pe=globalThis,ue=pe.ShadowRoot&&(pe.ShadyCSS===void 0||pe.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Te=Symbol(),qe=new WeakMap,X=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==Te)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(ue&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=qe.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&qe.set(e,s))}return s}toString(){return this.cssText}},Ve=n=>new X(typeof n=="string"?n:n+"",void 0,Te),ee=(n,...s)=>{let e=n.length===1?n[0]:s.reduce((t,i,o)=>t+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+n[o+1],n[0]);return new X(e,n,Te)},Ye=(n,s)=>{if(ue)n.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=pe.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,n.appendChild(t)}},Ce=ue?n=>n:n=>n instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return Ve(e)})(n):n;var{is:Tt,defineProperty:Ct,getOwnPropertyDescriptor:At,getOwnPropertyNames:Rt,getOwnPropertySymbols:Mt,getPrototypeOf:Pt}=Object,ge=globalThis,Je=ge.trustedTypes,Bt=Je?Je.emptyScript:"",Ht=ge.reactiveElementPolyfillSupport,te=(n,s)=>n,ie={toAttribute(n,s){switch(s){case Boolean:n=n?Bt:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,s){let e=n;switch(s){case Boolean:e=n!==null;break;case Number:e=n===null?null:Number(n);break;case Object:case Array:try{e=JSON.parse(n)}catch{e=null}}return e}},me=(n,s)=>!Tt(n,s),Qe={attribute:!0,type:String,converter:ie,reflect:!1,useDefault:!1,hasChanged:me};Symbol.metadata??=Symbol("metadata"),ge.litPropertyMetadata??=new WeakMap;var A=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=Qe){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&Ct(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:o}=At(this.prototype,s)??{get(){return this[e]},set(r){this[e]=r}};return{get:i,set(r){let a=i?.call(this);o?.call(this,r),this.requestUpdate(s,a,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??Qe}static _$Ei(){if(this.hasOwnProperty(te("elementProperties")))return;let s=Pt(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(te("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(te("properties"))){let e=this.properties,t=[...Rt(e),...Mt(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(Ce(i))}else s!==void 0&&e.push(Ce(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Ye(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let o=(t.converter?.toAttribute!==void 0?t.converter:ie).toAttribute(e,t.type);this._$Em=s,o==null?this.removeAttribute(i):this.setAttribute(i,o),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let o=t.getPropertyOptions(i),r=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:ie;this._$Em=i;let a=r.fromAttribute(e,o.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(s,e,t,i=!1,o){if(s!==void 0){let r=this.constructor;if(i===!1&&(o=this[s]),t??=r.getPropertyOptions(s),!((t.hasChanged??me)(o,e)||t.useDefault&&t.reflect&&o===this._$Ej?.get(s)&&!this.hasAttribute(r._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:o},r){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,r??e??this[s]),o!==!0||r!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,o]of this._$Ep)this[i]=o;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,o]of t){let{wrapped:r}=o,a=this[i];r!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,o,a)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};A.elementStyles=[],A.shadowRootOptions={mode:"open"},A[te("elementProperties")]=new Map,A[te("finalized")]=new Map,Ht?.({ReactiveElement:A}),(ge.reactiveElementVersions??=[]).push("2.1.2");var ze=globalThis,Ze=n=>n,_e=ze.trustedTypes,Xe=_e?_e.createPolicy("lit-html",{createHTML:n=>n}):void 0,nt="$lit$",P=`lit$${Math.random().toFixed(9).slice(2)}$`,rt="?"+P,zt=`<${rt}>`,j=document,oe=()=>j.createComment(""),ne=n=>n===null||typeof n!="object"&&typeof n!="function",Oe=Array.isArray,Ot=n=>Oe(n)||typeof n?.[Symbol.iterator]=="function",Ae=`[ \t
\f\r]`,se=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,et=/-->/g,tt=/>/g,z=RegExp(`>|${Ae}(?:([^\\s"'>=/]+)(${Ae}*=${Ae}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),it=/'/g,st=/"/g,at=/^(?:script|style|textarea|title)$/i,je=n=>(s,...e)=>({_$litType$:n,strings:s,values:e}),p=je(1),fe=je(2),si=je(3),L=Symbol.for("lit-noChange"),d=Symbol.for("lit-nothing"),ot=new WeakMap,O=j.createTreeWalker(j,129);function ct(n,s){if(!Oe(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return Xe!==void 0?Xe.createHTML(s):s}var jt=(n,s)=>{let e=n.length-1,t=[],i,o=s===2?"<svg>":s===3?"<math>":"",r=se;for(let a=0;a<e;a++){let l=n[a],g,v,_=-1,b=0;for(;b<l.length&&(r.lastIndex=b,v=r.exec(l),v!==null);)b=r.lastIndex,r===se?v[1]==="!--"?r=et:v[1]!==void 0?r=tt:v[2]!==void 0?(at.test(v[2])&&(i=RegExp("</"+v[2],"g")),r=z):v[3]!==void 0&&(r=z):r===z?v[0]===">"?(r=i??se,_=-1):v[1]===void 0?_=-2:(_=r.lastIndex-v[2].length,g=v[1],r=v[3]===void 0?z:v[3]==='"'?st:it):r===st||r===it?r=z:r===et||r===tt?r=se:(r=z,i=void 0);let y=r===z&&n[a+1].startsWith("/>")?" ":"";o+=r===se?l+zt:_>=0?(t.push(g),l.slice(0,_)+nt+l.slice(_)+P+y):l+P+(_===-2?a:y)}return[ct(n,o+(n[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},re=class n{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let o=0,r=0,a=s.length-1,l=this.parts,[g,v]=jt(s,e);if(this.el=n.createElement(g,t),O.currentNode=this.el.content,e===2||e===3){let _=this.el.content.firstChild;_.replaceWith(..._.childNodes)}for(;(i=O.nextNode())!==null&&l.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let _ of i.getAttributeNames())if(_.endsWith(nt)){let b=v[r++],y=i.getAttribute(_).split(P),$=/([.?@])?(.*)/.exec(b);l.push({type:1,index:o,name:$[2],strings:y,ctor:$[1]==="."?Me:$[1]==="?"?Pe:$[1]==="@"?Be:W}),i.removeAttribute(_)}else _.startsWith(P)&&(l.push({type:6,index:o}),i.removeAttribute(_));if(at.test(i.tagName)){let _=i.textContent.split(P),b=_.length-1;if(b>0){i.textContent=_e?_e.emptyScript:"";for(let y=0;y<b;y++)i.append(_[y],oe()),O.nextNode(),l.push({type:2,index:++o});i.append(_[b],oe())}}}else if(i.nodeType===8)if(i.data===rt)l.push({type:2,index:o});else{let _=-1;for(;(_=i.data.indexOf(P,_+1))!==-1;)l.push({type:7,index:o}),_+=P.length-1}o++}}static createElement(s,e){let t=j.createElement("template");return t.innerHTML=s,t}};function I(n,s,e=n,t){if(s===L)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,o=ne(s)?void 0:s._$litDirective$;return i?.constructor!==o&&(i?._$AO?.(!1),o===void 0?i=void 0:(i=new o(n),i._$AT(n,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=I(n,i._$AS(n,s.values),i,t)),s}var Re=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??j).importNode(e,!0);O.currentNode=i;let o=O.nextNode(),r=0,a=0,l=t[0];for(;l!==void 0;){if(r===l.index){let g;l.type===2?g=new ae(o,o.nextSibling,this,s):l.type===1?g=new l.ctor(o,l.name,l.strings,this,s):l.type===6&&(g=new He(o,this,s)),this._$AV.push(g),l=t[++a]}r!==l?.index&&(o=O.nextNode(),r++)}return O.currentNode=j,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},ae=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=I(this,s,e),ne(s)?s===d||s==null||s===""?(this._$AH!==d&&this._$AR(),this._$AH=d):s!==this._$AH&&s!==L&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):Ot(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==d&&ne(this._$AH)?this._$AA.nextSibling.data=s:this.T(j.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=re.createElement(ct(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let o=new Re(i,this),r=o.u(this.options);o.p(e),this.T(r),this._$AH=o}}_$AC(s){let e=ot.get(s.strings);return e===void 0&&ot.set(s.strings,e=new re(s)),e}k(s){Oe(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let o of s)i===e.length?e.push(t=new n(this.O(oe()),this.O(oe()),this,this.options)):t=e[i],t._$AI(o),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=Ze(s).nextSibling;Ze(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},W=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,o){this.type=1,this._$AH=d,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=o,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=d}_$AI(s,e=this,t,i){let o=this.strings,r=!1;if(o===void 0)s=I(this,s,e,0),r=!ne(s)||s!==this._$AH&&s!==L,r&&(this._$AH=s);else{let a=s,l,g;for(s=o[0],l=0;l<o.length-1;l++)g=I(this,a[t+l],e,l),g===L&&(g=this._$AH[l]),r||=!ne(g)||g!==this._$AH[l],g===d?s=d:s!==d&&(s+=(g??"")+o[l+1]),this._$AH[l]=g}r&&!i&&this.j(s)}j(s){s===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},Me=class extends W{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===d?void 0:s}},Pe=class extends W{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==d)}},Be=class extends W{constructor(s,e,t,i,o){super(s,e,t,i,o),this.type=5}_$AI(s,e=this){if((s=I(this,s,e,0)??d)===L)return;let t=this._$AH,i=s===d&&t!==d||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,o=s!==d&&(t===d||i);i&&this.element.removeEventListener(this.name,this,t),o&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},He=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){I(this,s)}};var Lt=ze.litHtmlPolyfillSupport;Lt?.(re,ae),(ze.litHtmlVersions??=[]).push("3.3.3");var lt=(n,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let o=e?.renderBefore??null;t._$litPart$=i=new ae(s.insertBefore(oe(),o),o,void 0,e??{})}return i._$AI(n),i};var Le=globalThis,T=class extends A{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=lt(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return L}};T._$litElement$=!0,T.finalized=!0,Le.litElementHydrateSupport?.({LitElement:T});var Dt=Le.litElementPolyfillSupport;Dt?.({LitElement:T});(Le.litElementVersions??=[]).push("4.2.2");var Nt={attribute:!0,type:String,converter:ie,reflect:!1,hasChanged:me},Ut=(n=Nt,s,e)=>{let{kind:t,metadata:i}=e,o=globalThis.litPropertyMetadata.get(i);if(o===void 0&&globalThis.litPropertyMetadata.set(i,o=new Map),t==="setter"&&((n=Object.create(n)).wrapped=!0),o.set(e.name,n),t==="accessor"){let{name:r}=e;return{set(a){let l=s.get.call(this);s.set.call(this,a),this.requestUpdate(r,l,n,!0,a)},init(a){return a!==void 0&&this.C(r,void 0,n,a),a}}}if(t==="setter"){let{name:r}=e;return function(a){let l=this[r];s.call(this,a),this.requestUpdate(r,l,n,!0,a)}}throw Error("Unsupported decorator location: "+t)};function q(n){return(s,e)=>typeof e=="object"?Ut(n,s,e):((t,i,o)=>{let r=i.hasOwnProperty(o);return i.constructor.createProperty(o,t),r?Object.getOwnPropertyDescriptor(i,o):void 0})(n,s,e)}function B(n){return q({...n,state:!0,attribute:!1})}var D=n=>Math.max(0,Math.min(75,n));function De(n,s="theme"){let e=D(n.upper.angle??0),t=D(n.lower.angle??0),i=`rotate(${e} 150 70)`,o=`rotate(${-t} 150 70)`,r=a=>a.angle===void 0?"":`${a.label?`${a.label} `:""}${Math.round(D(a.angle))}\xB0`;return fe`
    <svg
      class="bed-graphic bed-graphic-${s} ${n.moving?"is-moving":""}"
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
        <g class="bed-panel" transform=${o}>
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
  `}function Ne(n){let s=D(n.left.upper.angle??0),e=D(n.left.lower.angle??0),t=D(n.right.upper.angle??0),i=D(n.right.lower.angle??0),o=(r,a,l,g)=>fe`
    <g
      class="dual-bed-side dual-bed-side-${r} ${g?"is-moving":""}"
      fill=${`url(#abDual${r==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel"
        transform=${`rotate(${-l} 150 70)`}
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
  `;return fe`
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
      ${o("right",t,i,n.right.moving)}
      ${o("left",s,e,n.left.moving)}
    </svg>
  `}function Ue(n){let s=n.find(t=>t.key==="back"||t.key==="head"),e=n.find(t=>t.key==="legs"||t.key==="feet");return s&&e?{upper:s,lower:e}:void 0}function dt(n,s){let e=n.motors.filter(t=>{let i=t.angle??t.position;return s.states[i??""]?.attributes.unit_of_measurement==="\xB0"});return Ue(e)!==void 0}function ht(n,s){let e=n?.entities[s]?.device_id,t=n?.states[s]?.attributes,i=t?.held_control,o=t?.hold_start_delay_ms,r=t?.hold_release_delay_ms;if(!(!e||typeof i!="string"||typeof o!="number"||!Number.isFinite(o)||o<0||typeof r!="number"||!Number.isFinite(r)||r<0))return{key:s,up:s,deviceId:e,holdEntityId:s,heldControl:{control:i,startDelayMs:o,releaseDelayMs:r}}}function pt(n,s,e){if(s.timedMove)return n?.callService("adjustable_bed","timed_move",{device_id:s.timedMove.deviceId,side:"both",motor:s.timedMove.motor,direction:e,duration_ms:1e3});if(s.cover)return n?.callService("cover",e==="up"?"open_cover":"close_cover",{entity_id:s.cover});let t=e==="up"?s.up:s.down;return t?n?.callService("button","press",{entity_id:t}):void 0}function ut(n,s,e){let t=s.heldControls?.[e]??s.heldControl;if(!t||!s.deviceId)return;let i=n?.states[s.holdEntityId??s.cover??""]?.attributes.bed_side,o={device_id:[s.deviceId],control:t.control,duration:60};return(i==="left"||i==="right"||i==="both")&&(o.side=i),n?.callService("adjustable_bed","hold_control",o)}var be=class{constructor(s,e={setTimeout:(t,i)=>globalThis.setTimeout(t,i),clearTimeout:t=>globalThis.clearTimeout(t)}){this.actions=s;this.timers=e;this._key=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0;this._started=!1;this._releaseId=0;this._pendingReleases=new Map}get heldKey(){return this._key}start(s,e,t,i){if(this._key!==null)return;this._key=s.key,this._cover=s.cover??null,this._stop=i??null,this._pointerId=t;let o=++this._generation;if(this._heldControl=s.heldControls?.[e]??s.heldControl,this._flushPendingForTarget(this._targetKey()),this._heldControl){let r=this._heldControl.startDelayMs;r<=0?this._startHeldControl(s,e,o):this._startTimer=this.timers.setTimeout(()=>this._startHeldControl(s,e,o),r);return}this._started=!0,this._repeat(s,e,o)}_startHeldControl(s,e,t){this._startTimer=void 0,!(t!==this._generation||this._key!==s.key)&&(this._started=!0,this._holdControl(s,e,t))}async _holdControl(s,e,t){try{let i=this.actions.holdControl(s,e);i&&await i}catch{}finally{t===this._generation&&this._reset()}}async _repeat(s,e,t){for(;t===this._generation;)try{let i=this.actions.pulse(s,e);if(!i)return;await i}catch{return}}_targetKey(s=this._stop??void 0,e=this._cover??void 0){return s??e??this._key??""}_release(s){s.cover?this.actions.stopCover(s.cover,s.stopEntityId):this.actions.stopBed(s.stopEntityId)}_scheduleRelease(){let s={id:++this._releaseId,motorKey:this._key??"",targetKey:this._targetKey(),cover:this._cover??void 0,stopEntityId:this._stop??void 0};this._pendingReleases.set(s.id,s);let e=this._heldControl?.releaseDelayMs??0;if(e<=0){this._runRelease(s);return}s.timer=this.timers.setTimeout(()=>this._runRelease(s),e)}_runRelease(s){this._pendingReleases.delete(s.id)&&(s.timer!==void 0&&this.timers.clearTimeout(s.timer),this._release(s))}_flushPendingForTarget(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s&&(this._runRelease(t),e.add(i))}return e}_flushAllReleases(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s?(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer)):(this._runRelease(t),e.add(i))}return e}_discardReleasesForTarget(s){for(let e of[...this._pendingReleases.values()])e.targetKey===s&&(this._pendingReleases.delete(e.id),e.timer!==void 0&&this.timers.clearTimeout(e.timer))}_discardAllReleases(){for(let s of this._pendingReleases.values())s.timer!==void 0&&this.timers.clearTimeout(s.timer);this._pendingReleases.clear()}endFromPointer(s,e,t){this._pointerId!==null&&e!==this._pointerId||t&&this.end(s)}end(s){if(this._key!==s.key)return;let e=this._started,t=this._heldControl!==void 0,i={cover:this._cover??void 0,stopEntityId:this._stop??void 0};e&&t&&this._scheduleRelease(),this._reset(),!(!e||t)&&this._release(i)}cancel(s,e=!1){if(!s)return!1;let t=this._key===s.key;t&&this._reset();let i=!1;if(e)for(let o of[...this._pendingReleases.values()])o.motorKey===s.key&&(this._pendingReleases.delete(o.id),o.timer!==void 0&&this.timers.clearTimeout(o.timer),i=!0);return t||i}stopAll(s,e=!1){if(s!==void 0){e?(this._discardAllReleases(),this._reset()):(this._discardReleasesForTarget(s),this._key!==null&&this._targetKey()===s&&this._reset()),this.actions.stopBed(s);return}let t=this._flushAllReleases(s),i=this._key===null?null:{cover:this._cover??void 0,stopEntityId:this._stop??void 0},o=i?this._targetKey(i.stopEntityId,i.cover):void 0,r=this._started;this._reset(),i&&r&&o!==void 0&&(this._release(i),t.add(o)),t.size===0&&(!i||!r)&&this.actions.stopBed(i?.stopEntityId)}abandon(){let s=this._key===null?null:{cover:this._cover??void 0,stopEntityId:this._stop??void 0},e=this._started;this._reset(),s&&e&&this._release(s),this._flushAllReleases()}_reset(){this._startTimer!==void 0&&this.timers.clearTimeout(this._startTimer),this._startTimer=void 0,this._key=null,this._cover=null,this._stop=null,this._pointerId=null,this._started=!1,this._heldControl=void 0,this._generation++}};function gt(n,s,e){let t=()=>n.abandon(),i=()=>{s.visibilityState==="hidden"&&t()};return s.addEventListener("visibilitychange",i),e.addEventListener("pagehide",t),()=>{s.removeEventListener("visibilitychange",i),e.removeEventListener("pagehide",t)}}var mt={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Actions","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"A \xB7 Glance only","editor.recipe_quick":"B \xB7 Quick actions","editor.recipe_controls":"C \xB7 Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Default / fixed target","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both"};var _t={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Handlinger","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"A \xB7 Kun oversikt","editor.recipe_quick":"B \xB7 Hurtighandlinger","editor.recipe_controls":"C \xB7 Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Standard / fast m\xE5l","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge"};var N={en:mt,nb:_t};function Gt(n){let s=(n?.locale?.language||n?.language||"en").toLowerCase(),e=s.split("-")[0];return N[s]?N[s]:N[e]?N[e]:e==="nn"||e==="no"?N.nb:N.en}function u(n,s,e){let i=Gt(n)[s]??N.en[s]??s;if(e)for(let[o,r]of Object.entries(e))i=i.replace(`{${o}}`,r);return i}var ft=["glance","quick","controls"];function vt(n,s){let e={...n,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:s==="glance"?"names":"angles",show_side_selector:!0,show_motors:s==="controls",show_lighting:!1,show_connection:!1,animate:!0};return s==="glance"?e.compact_actions=[]:delete e.compact_actions,e}function Fe(n,s){return[...s.presets,...s.memory.flatMap(e=>e.goto?[e.goto]:[])].flatMap(e=>{let t=n.entities[e]?.translation_key;return t?[{key:Q(t).key,entityId:e}]:[]})}function ye(n,s,e){let t=Fe(n,s);if(e){let r=new Map(t.map(a=>[a.key,a]));return[...new Set(e)].flatMap(a=>{let l=r.get(a);return l?[l]:[]})}let i=t.find(r=>r.key==="preset_flat"),o=t.find(r=>r.key.startsWith("preset_memory_"))??t.find(r=>r!==i);return[i,o].filter(r=>r!==void 0)}function $e(n){return n.stop?[n.stop]:n.motors.flatMap(s=>s.cover?[s.cover]:[])}function xe(n){if(!(!n||!n.startsWith("/")||/^\/[/\\]/.test(n)||/[\\\s]/.test(n)))return n}function we(n,s){let e=de(n,s),t=Z(n,e);return e&&t.length?[{key:"both",label:u(n,"card.both_sides"),bed:k(n,e)},...t.map(i=>({key:i,label:n.devices[i]?.name_by_user??n.devices[i]?.name??i,bed:k(n,i)}))]:le(n,s)?["both","left","right"].map(i=>({key:i,label:u(n,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:k(n,s,i)})):[{key:"both",label:u(n,"card.both_sides"),bed:k(n,s)}]}var bt="4.2.4";function yt(n,s){return{graphic:dt(n,s),motors:n.motors.some(e=>e.cover||e.up||e.down)||!!n.stop||!!n.synchro,firmness:n.firmness.length>0,presets:n.presets.length>0,memory:n.memory.length>0,lighting:G(n.lights)||!!n.lights.state,massage:n.massage.buttons.length>0||n.massage.numbers.length>0||!!n.massage.states?.length||!!n.massage.selects?.length||!!n.massage.timer,utility:n.utility.length>0,climate:n.climate.entities.length>0||n.climate.selects.length>0||n.climate.numbers.length>0,connection:!!(n.connect||n.disconnect)}}var It="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",Wt="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",qt=(n,s)=>n.length===s.length&&n.every((e,t)=>e===s[t]),V=class extends T{constructor(){super(...arguments);this._computeLabel=e=>u(this.hass,`editor.${e.name}`)}setConfig(e){this._config=e}_bed(){let e=this._config?.device_id;if(!this.hass||!e)return;let t=we(this.hass,e).map(r=>r.bed),i=t[0];if(!i)return;let o=new Map;for(let r of t)for(let a of r.memory){let l=o.get(a.slot);o.set(a.slot,{slot:a.slot,goto:l?.goto??a.goto,save:l?.save??a.save})}return{...i,memory:[...o.values()].sort((r,a)=>r.slot-a.slot)}}_presentKeys(e){let t=this.hass?we(this.hass,this._config?.device_id).map(i=>i.bed):[e];return K.filter(i=>t.some(o=>yt(o,this.hass)[i]))}_orderedKeys(e){let t=this._presentKeys(e),o=(this._config?.section_order??[]).filter(a=>t.includes(a)),r=t.filter(a=>!o.includes(a));return[...o,...r]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=t&&this.hass?.states[t]?.attributes.friendly_name||`Memory ${e.slot}`,o=t&&this.hass?.entities[t]?.device_id,r=o?this.hass?.devices[o]:void 0,a=r?.name_by_user||r?.name;return a&&i.startsWith(`${a} `)?i.slice(a.length+1):i}_emit(e){e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;i.device_id!==t.device_id&&delete i.default_target,i.device_id=t.device_id||void 0,t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let o=this._orderedKeys(e),r=o.indexOf(t),a=r+i;if(r<0||a<0||a>=o.length)return;[o[r],o[a]]=[o[a],o[r]];let l=this._cfg;qt(o,this._presentKeys(e))?delete l.section_order:l.section_order=o,this._emit(l)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let o=this._memorySlots(e),r=this._config?.memory_slots,a=r&&r.length?r.map(Number):[...o];i?a.includes(t)||a.push(t):a=a.filter(g=>g!==t),a.sort((g,v)=>g-v);let l=this._cfg;a.length===o.length?delete l.memory_slots:l.memory_slots=a,this._emit(l)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?p`
      <div class="group">
        <div class="group-title">${u(this.hass,"editor.sections")}</div>
        ${t.map((i,o)=>{let r=this._config?.[`show_${i}`]!==!1;return p`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${o===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${u(this.hass,"editor.move_up")}
                  aria-label=${u(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${It}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${o===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${u(this.hass,"editor.move_down")}
                  aria-label=${u(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Wt}></path></svg>
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
    `:d}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return d;let i=e.memory.some(r=>r.save),o=e.memory.length>1;return!i&&!o?d:p`
      <div class="group">
        <div class="group-title">
          ${u(this.hass,"editor.memory_group")}
        </div>
        ${i?p`<div class="row">
                <span class="label">${u(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                ></ha-switch>
              </div>`:d}
        ${o?p`<div class="sub">
                <div class="sub-label">
                  ${u(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(r=>p`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${a=>this._toggleSlot(e,r.slot,a.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(r)}</span>
                    </label>
                  `)}
              </div>`:d}
      </div>
    `}_setOption(e,t){this._emit({...this._cfg,[e]:t})}_compactToggle(e,t){return p`<div class="row"><span class="label">${u(this.hass,e==="show_connection"?"editor.compact_connection":`editor.${e}`)}</span>
      <ha-switch .checked=${this._config?.[e]??t}
        @change=${i=>this._setOption(e,i.target.checked)}></ha-switch>
    </div>`}_compactGroup(){let e=this._config,t=we(this.hass,e.device_id),i=t.find(l=>l.key===(e.default_target??"both")),o=t.flatMap(l=>Fe(this.hass,l.bed)).filter((l,g,v)=>v.findIndex(_=>_.key===l.key)===g),r=e.compact_actions??(i?ye(this.hass,i.bed).map(l=>l.key):[]),a=[...r.filter(l=>o.some(g=>g.key===l)),...o.map(l=>l.key).filter(l=>!r.includes(l))];return p`
      <div class="group">
        <div class="group-title">${u(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        <label class="row"><span class="label">${u(this.hass,"editor.compact_labels")}</span>
          <select .value=${e.compact_labels??"angles"}
            @change=${l=>this._setOption("compact_labels",l.target.value)}>
            ${["angles","names","none"].map(l=>p`
              <option value=${l}>${u(this.hass,`editor.labels_${l}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        <label class="row path-row"><span class="label">${u(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${e.navigation_path??""} placeholder="/dashboard/bed"
            @change=${l=>this._setOption("navigation_path",l.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${u(this.hass,"editor.compact_controls")}</div>
        ${t.length>1||!i?p`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${u(this.hass,"editor.default_target")}</span>
            <select .value=${e.default_target??"both"}
              @change=${l=>this._setOption("default_target",l.target.value)}>
              ${i?d:p`<option value=${e.default_target}>${u(this.hass,"compact.target_missing")}</option>`}
              ${t.map(l=>p`<option value=${l.key}>${l.label}</option>`)}
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
        ${a.map(l=>{let g=o.find($=>$.key===l),v=r.includes(l),_=r.indexOf(l),b=$=>{let E=[...r];[E[_],E[_+$]]=[E[_+$],E[_]],this._setOption("compact_actions",E)},y=this.hass.states[g.entityId];return p`<div class="row">
            <ha-checkbox .checked=${v} @change=${$=>this._setOption("compact_actions",$.target.checked?[...r,l]:r.filter(E=>E!==l))}></ha-checkbox>
            <span class="label">${y?.attributes.friendly_name??l}</span>
            <button class="icon-btn" ?disabled=${!v||_===0}
              aria-label=${u(this.hass,"editor.move_up")} @click=${()=>b(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!v||_===r.length-1}
              aria-label=${u(this.hass,"editor.move_down")} @click=${()=>b(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return p`<div class="group">
      <label class="row"><span class="label">${u(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${e=>this._setOption("layout",e.target.value)}>
          <option value="full">${u(this.hass,"editor.layout_full")}</option>
          <option value="compact">${u(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${u(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${ft.map(e=>p`
        <button @click=${()=>this._emit({...vt(this._config,e)})}>
          ${u(this.hass,`editor.recipe_${e}`)}
        </button>`)}</div>
    </div>`}render(){if(!this.hass||!this._config)return d;let e=this._bed();return p`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():p`
        ${e?this._sectionsGroup(e):d}
        ${e?this._memoryGroup(e):d}
      `}
    `}};V.styles=ee`
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
  `,S([q({attribute:!1})],V.prototype,"hass",2),S([B()],V.prototype,"_config",2);he("adjustable-bed-card-editor",V);var Vt=new Set(["back","legs","head","feet"]),C=class extends T{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._watched=[];this._compactStopTargets=new Map;this._hold=new be({pulse:(e,t)=>pt(this.hass,e,t),holdControl:(e,t)=>ut(this.hass,e,t),stopCover:(e,t)=>this._stopCompactTarget(e,t??e),stopBed:e=>{e&&this._stopCompactTarget(e)}});this._navigate=()=>{let e=xe(this._config?.navigation_path);e&&(this._hold.abandon(),history.pushState(null,"",e),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))}}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===H)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config&&(this._hold.abandon(),this._stopCompact()),(e.device_id!==this._config?.device_id||e.default_target!==this._config?.default_target)&&(this._activePairedPane=e.default_target??"both"),this._config=e}getCardSize(){if(this._config?.layout!=="compact")return 8;let e=this._config;return Math.ceil((24+(e.show_header!==!1?36:0)+(e.show_graphic!==!1?150:0)+(e.compact_labels!=="none"?40:0)+(e.compact_actions?.length===0?0:110)+(e.show_motors===!0?180:0)+(e.show_lighting===!0?70:0)+(e.show_connection===!0?50:0))/50)}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}connectedCallback(){super.connectedCallback(),this._removeHoldLifecycle=gt(this._hold,document,window)}disconnectedCallback(){this._removeHoldLifecycle?.(),this._removeHoldLifecycle=void 0,super.disconnectedCallback(),this._hold.abandon()}shouldUpdate(e){if(e.has("_config")||e.has("_saveModeFor")||e.has("_activePairedPane")||e.has("_synchronizingTo")||e.has("_synchronizationFailed")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices)return!0;for(let i of this._watched)if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return d;if(!this._config.device_id)return this._notice("card.no_device");let e=de(this.hass,this._config.device_id),t=Z(this.hass,e);if(e&&t.length)return this._renderPaired(e,t);if(this._config.device_id&&le(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=k(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),M(i)?this._notice("card.no_entities"):this._config.layout==="compact"?this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:i}],!1):p`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(e,t="theme",i){let o=this._config,r={graphic:()=>o.show_graphic!==!1?i??this._graphic(e,t):d,motors:()=>o.show_motors!==!1?this._motors(e):d,firmness:()=>o.show_firmness!==!1?this._firmness(e):d,presets:()=>o.show_presets!==!1?this._presets(e):d,memory:()=>o.show_memory!==!1?this._memory(e):d,lighting:()=>o.show_lighting!==!1?this._lighting(e):d,massage:()=>o.show_massage!==!1?this._massage(e):d,utility:()=>o.show_utility!==!1?this._utility(e):d,climate:()=>o.show_climate!==!1?this._climate(e):d,connection:()=>o.show_connection!==!1?this._connection(e):d};return this._orderedSections().map(a=>r[a]?.()??d)}_renderPaired(e,t){let i=this.hass,o=k(i,e),r=t.map((a,l)=>({key:a,label:this._deviceLabel(a),bed:k(i,a),graphicTone:l===0?"left":"right",synchronizationTarget:{deviceId:a}}));return this._watched=[o,...r.map(a=>a.bed)].flatMap(a=>this._collectWatched(a)),M(o)&&r.every(a=>M(a.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:u(i,"card.both_sides"),bed:o},...r])}_renderSingleAddressPaired(e){let t=this.hass,i={both:k(t,e,"both"),left:k(t,e,"left"),right:k(t,e,"right")};return this._watched=Object.values(i).flatMap(o=>this._collectWatched(o)),Object.values(i).every(o=>M(o))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:u(t,"card.both_sides"),bed:i.both},{key:"left",label:u(t,"card.left_side"),bed:i.left,graphicTone:"left",synchronizationTarget:{deviceId:e,side:"left"}},{key:"right",label:u(t,"card.right_side"),bed:i.right,graphicTone:"right",synchronizationTarget:{deviceId:e,side:"right"}}])}_renderPairedCard(e,t){if(this._config?.layout==="compact")return this._renderCompact(e,t,!0);let i=t.filter(l=>!M(l.bed)),o=i.find(l=>l.key===this._activePairedPane)??i[0],r=i.filter(l=>l.key!=="both"),a=o.key==="both";return p`
      <ha-card class="paired-card">
        ${this._header(o.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(l=>p`
              <button
                class="pane-tab side-${l.graphicTone??"theme"} ${l.key===o.key?"active":""}"
                role="tab"
                aria-selected=${l.key===o.key?"true":"false"}
                @click=${()=>this._selectPairedPane(l.key)}
              >
                ${l.graphicTone?p`<span class="dual-swatch" aria-hidden="true"></span>`:d}
                <span>${l.key==="both"?u(this.hass,"card.both"):l.label}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${o.label}>
          ${this._renderSections(o.bed,o.graphicTone,a?this._pairedOverview(r):void 0)}
          ${a&&this._config?.show_lighting!==!1?this._combinedLighting(o.bed,r):d}
          ${a&&this._config?.show_connection!==!1?this._combinedBluetooth(r):d}
        </div>
      </ha-card>
    `}_renderCompact(e,t,i){let o=this._config,r=t.find(f=>f.key===this._activePairedPane),a=r?.bed,l=a?ye(this.hass,a,o.compact_actions):[],g=o.show_motors===!0&&a?a.motors.filter(f=>f.cover||f.up||f.down||f.position):[],v=l.length>0||g.length>0||o.show_lighting===!0,_=o.compact_actions?.length!==0||o.show_motors===!0||o.show_lighting===!0,b=i?t.filter(f=>f.key!=="both"):t,y=!!a&&$e(a).length>0,$=l.length>0||g.length>0,E=xe(o.navigation_path);return p`
      <ha-card class="compact-card ${_?"":"compact-glance"} ${o.animate===!1?"no-animation":""}">
        ${o.show_header!==!1?p`
          <div class="compact-header">
            <span class="title">${this._title(e)}</span>
            ${E?p`<button class="compact-open" @click=${this._navigate}
              aria-label=${u(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:d}
          </div>`:d}
        ${i&&_?o.show_side_selector!==!1?p`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${t.filter(f=>!M(f.bed)).length}`}
            aria-label=${u(this.hass,"compact.target")}>
            ${t.filter(f=>!M(f.bed)).map(f=>p`
              <button class="pane-tab side-${f.graphicTone??"theme"} ${f.key===r?.key?"active":""}"
                aria-pressed=${f.key===r?.key?"true":"false"}
                title=${f.label}
                @click=${()=>this._selectPairedPane(f.key)}>
                ${f.graphicTone?p`<span class="dual-swatch" aria-hidden="true"></span>`:d}
                <span class="compact-tab-label">${f.key==="both"?u(this.hass,"card.both"):f.label}</span>
              </button>`)}
          </div>`:p`<div class="compact-target">
            ${u(this.hass,"compact.target")}: ${r?.label??u(this.hass,"compact.target_missing")}
          </div>`:d}
        ${o.show_graphic!==!1?this._compactGraphic(b):d}
        ${this._compactReadouts(b)}
        ${!r&&_?p`<div class="hint" role="status">
          ${u(this.hass,"compact.target_missing")}</div>`:d}
        ${g.length?p`<div class="rows compact-motors">
          ${g.map(f=>f.cover||f.up||f.down?this._motorRow(f,a?.stop,!0):this._moreInfoRow(f.position))}
        </div>`:d}
        ${l.length||$||this._compactStopTargets.size?p`
          <div class="tiles compact-actions">
            ${l.map(({entityId:f})=>p`<button class="tile"
              ?disabled=${!y||!this._available(f)}
              @click=${()=>this._compactRecall(f,a)}>
              ${this._icon(f)}<span class="tile-label">${this._name(f)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!y&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(a)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${u(this.hass,"action.stop")}</span>
            </button>
          </div>`:d}
        ${o.show_lighting===!0&&a?p`
          ${this._lighting(a)}
          ${i&&r?.key==="both"?this._combinedLighting(a,b):d}
        `:d}
        ${o.show_connection===!0?i&&r?.key==="both"?this._combinedBluetooth(b):p`<div class="compact-connections">
          ${b.map(f=>{let m=this._connectionStatus(f.bed);return m?p`<span>${this._connectionDot(f.bed)}
              ${f.label}: ${u(this.hass,`status.${m}`)}</span>`:d})}
        </div>`:d}
        ${!v&&o.show_graphic===!1&&o.compact_labels==="none"&&o.show_header===!1&&o.show_connection!==!0?p`<div class="hint">${this._title(e)}</div>`:d}
      </ha-card>`}_compactGraphic(e){let t=e.map(g=>this._graphicState(g.bed)),i=t[0],o=t[1],r=t.length>0&&t.every(g=>g!==void 0),a=e.map((g,v)=>`${g.label}: ${t[v]?this._positionSummary(t[v]):u(this.hass,"compact.no_position")}`).join(". "),l=r&&i?o?Ne({left:i,right:o}):De({...i,upper:{angle:i.upper.angle},lower:{angle:i.lower.angle}}):p`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${u(this.hass,"compact.no_position")}</span></div>`;return xe(this._config?.navigation_path)?p`<button class="compact-graphic" @click=${this._navigate}
          aria-label="${u(this.hass,"compact.open")}. ${a}">${l}</button>`:p`<div class="compact-graphic" role="img" aria-label=${a}>${l}</div>`}_compactReadouts(e){let t=this._config?.compact_labels??"angles";return t==="none"?d:p`<div class="compact-readouts ${t==="names"?"compact-names":""}">
      ${e.map(i=>p`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span aria-label=${i.label}>${t==="angles"&&e.length>1?[...i.label][0]:i.label}</span>
        </span>
        ${t==="angles"?p`<span class="compact-position"
          title=${i.bed.motors.map(o=>`${this._motorName(o)} ${this._readout(o)??"?"}`).join(" \xB7 ")}
        >${i.bed.motors.filter(o=>o.angle||o.position||o.cover).map(o=>this._readout(o)??"?").join(" / ")||u(this.hass,"compact.no_position")}</span>`:d}
      </div>`)}
    </div>`}_available(e){let t=this._state(e)?.state;return t!==void 0&&t!=="unavailable"}_compactRecall(e,t){this._hold.abandon(),$e(t).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(e),this.requestUpdate()}_stopCompact(e){this._hold.abandon();for(let t of e?$e(e):[])this._compactStopTargets.has(t)||this._compactStopTargets.set(t,Symbol());for(let t of this._compactStopTargets.keys())this._stopCompactTarget(t);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(e,t=e){let i=this._compactStopTargets.get(t),o=e.startsWith("cover.");this.hass?.callService(o?"cover":"button",o?"stop_cover":"press",{entity_id:e}).then(()=>{i!==void 0&&this._compactStopTargets.get(t)===i&&(this._compactStopTargets.delete(t),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(e){this._activePairedPane!==e&&(this._hold.abandon(),this._activePairedPane=e,this._saveModeFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(e){if(!e.connectivity)return;let t=this._state(e.connectivity);return t?.attributes?.state_detail==="connecting"?"connecting":t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(e){let t=this._connectionStatus(e);return t?p`<span
      class="connection-dot ${t}"
      title=${u(this.hass,`status.${t}`)}
    ></span>`:d}_pairedOverview(e){let t=e.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(t.length<2)return d;let[i,o]=t;return p`
      <div class="graphic dual-graphic">
        ${Ne({left:i.graphic,right:o.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,o].map(({pane:r,graphic:a},l)=>p`
            <div class="dual-readout side-${l===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${r.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(a)}
              </span>
            </div>
          `)}
      </div>
      ${this._synchronizeSelector(i.pane,o.pane)}
    `}_synchronizeSelector(e,t){if(!e.synchronizationTarget||!t.synchronizationTarget)return d;let i=this._synchronizationPlan(e.bed,t.bed),o=this._synchronizationPlan(t.bed,e.bed);if(i.length===0&&o.length===0)return d;let r=this._synchronizingTo!==void 0;return p`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${u(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${u(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"left")}
          >
            ${this._synchronizingTo==="left"?p`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:p`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${u(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||o.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"right")}
          >
            ${this._synchronizingTo==="right"?p`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:p`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?p`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${u(this.hass,"sync.incomplete")}</span>
          </div>`:d}
    `}_synchronizationPlan(e,t){let i=new Map(t.motors.map(a=>[a.key,a])),o=e.motors.filter(a=>Vt.has(a.key)&&i.has(a.key)&&this._hasPositionFeedback(a)&&this._hasPositionFeedback(i.get(a.key)));if(o.length===0)return[];let r=o.map(a=>({motor:a.key,position:this._angle(a)}));return r.some(a=>a.position===void 0)||o.some(a=>this._angle(i.get(a.key))===void 0)?[]:r}_hasPositionFeedback(e){return e.angle!==void 0||e.position!==void 0}async _synchronizePositions(e,t,i){if(this._synchronizingTo||!this.hass)return;let o=i==="left"?e:t,r=i==="left"?t:e,a=r.synchronizationTarget;if(!a)return;let l=this._synchronizationPlan(o.bed,r.bed);if(l.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(H,"set_positions",{device_id:[a.deviceId],positions:l,...a.side?{side:a.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(e){return(e.upperMotor===e.lowerMotor?[e.upperMotor]:[e.upperMotor,e.lowerMotor]).map(i=>{let o=this._readout(i);return o?`${this._motorName(i)} ${o}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(e,t){if(this._hasLighting(e))return d;let i=t.map(v=>this._mainLight(v.bed)).filter(v=>v!==void 0);if(i.length===0)return d;let o=i.filter(v=>this._state(v)?.state==="on").length,r=o===i.length,a=o>0,l=r?"combined.on":a?"combined.mixed":"combined.off",g=u(this.hass,"combined.lights");return p`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${a?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${g}</span>
          <span class="secondary">${u(this.hass,l)}</span>
        </div>
        <button
          class="toggle ${a?"on":""} ${a&&!r?"mixed":""}"
          role="switch"
          aria-label=${g}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(e){let t=e.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return t.length===0?d:p`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${t.map(({pane:i,entityId:o})=>{let r=this._connectionStatus(i.bed),l=this._state(o)?.attributes.rssi;return p`
            <div class="bluetooth-receiver" role="group" aria-label=${i.label}>
            <button
              class="bluetooth-status ${r}"
              @click=${()=>this._moreInfo(o)}
            >
              <ha-icon
                icon=${r==="connected"?"mdi:bluetooth-connect":r==="connecting"?"mdi:bluetooth-transfer":r==="idle"?"mdi:bluetooth":"mdi:bluetooth-off"}
              ></ha-icon>
              <span class="bluetooth-copy">
                <span>${i.label}</span>
                <span class="bluetooth-detail">
                  ${u(this.hass,`status.${r}`)}${typeof l=="number"?` \xB7 ${l} dBm`:""}
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
    `}_mainLight(e){return e.lights.light??e.lights.switch}_hasLighting(e){return G(e.lights)}_deviceLabel(e){let t=this.hass?.devices[e];return t?.name_by_user??t?.name??e}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...K];let t=new Set(K),i=e.filter(r=>t.has(r)),o=K.filter(r=>!i.includes(r));return[...i,...o]}_header(e,t){let i=this._connectionStatus(e),o={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return p`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${i===void 0?d:p`
                <button
                  class="conn ${o[i].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${u(this.hass,o[i].key)}
                >
                  <ha-icon icon=${o[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e,t="theme"){let i=this._graphicState(e);return i?p`
      <div class="graphic">
        ${De(i,t)}
      </div>
    `:d}_graphicState(e){let t=e.motors.filter(l=>{let g=l.angle??l.position;return g!==void 0&&this._state(g)?.attributes.unit_of_measurement==="\xB0"});if(t.length===0||t.some(l=>this._angle(l)===void 0))return;let i=Ue(t);if(!i)return;let{upper:o,lower:r}=i,a=e.motors.some(l=>{let g=l.cover?this._state(l.cover)?.state:void 0;return g==="opening"||g==="closing"});return{upperMotor:o,lowerMotor:r,upper:{label:this._motorName(o),angle:this._angle(o)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:a}}_motors(e){let t=e.motors.filter(r=>r.cover||r.up||r.down),i=e.motors.filter(r=>r.position&&!r.cover&&!r.up&&!r.down);if(t.length===0&&i.length===0&&!e.synchro&&!e.controlSide&&!e.stop)return d;let o=t.length>0||i.length>0||!!e.synchro||!!e.controlSide;return p`
      ${o?this._heading("section.position"):d}
      ${e.controlSide?this._moreInfoRow(e.controlSide):d}
      ${e.synchro?this._toggleRow(e.synchro):d}
      ${t.length?p`<div class="rows">
              ${t.map(r=>this._motorRow(r,e.stop))}
            </div>`:d}
      ${i.length?p`<div class="rows">
              ${i.map(r=>this._moreInfoRow(r.position))}
            </div>`:d}
      ${e.stop?p`<button class="stop-all" @click=${()=>this._hold.stopAll(e.stop,this._stopCoversAllTargets(e.stop))}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${u(this.hass,"action.stop_all")}</span>
            </button>`:d}
    `}_firmness(e){return e.firmness.length===0?d:p`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t,i=!1){let o=this._readout(e),r=!!e.cover||!!t,a=p`
      <span>${this._motorName(e)}</span>
      ${o&&!i?p`<span class="readout">${o}</span>`:d}
    `;return p`
      <div class="row">
        ${e.position?p`<button
              class="row-label position-label"
              aria-label=${this._name(e.position)}
              @click=${()=>this._moreInfo(e.position)}
            >${a}</button>`:p`<div class="row-label">${a}</div>`}
        <div class="control-group">
          ${i?this._motorDirection(e,"down",t):d}
          ${this._motorDirection(e,"up",t)}
          ${i?d:p`<button
            class="cg-btn"
            aria-label=${u(this.hass,"action.stop")}
            @click=${()=>this._motorStop(e,t)}
            ?disabled=${!r}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?d:this._motorDirection(e,"down",t)}
        </div>
      </div>
    `}_motorDirection(e,t,i){let o=e.cover??e[t],r=!!e.cover||!!i;return p`
      <button class="cg-btn"
        aria-label=${u(this.hass,`action.${t}`)}
        @pointerdown=${a=>this._startHold(a,e,t,i)}
        @pointerup=${a=>this._endPointerHold(a,e)}
        @pointercancel=${a=>this._endPointerHold(a,e)}
        @keydown=${a=>this._startHold(a,e,t,i)}
        @keyup=${a=>this._endKeyHold(a,e)}
        @blur=${()=>this._endHold(e)}
        @click=${a=>this._activateWithoutPointer(a,e,t,i)}
        ?disabled=${!o||this._config?.layout==="compact"&&(!r||!this._available(o))}
      ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`}_presets(e){return e.presets.length===0?d:p`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._actionTile(t,e.stop))}
      </div>
    `}_utility(e){return e.utility.length===0&&!e.utilityNumbers?.length&&!e.utilitySelects?.length&&!e.utilityStates?.length?d:p`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${e.utility.map(t=>this._actionTile(t,e.stop,()=>t.startsWith("switch.")?this._call("switch","toggle",t):this._press(t)))}
      </div>
      ${e.utilitySelects?.map(t=>this._moreInfoRow(t))}
      ${e.utilityNumbers?.map(t=>this._moreInfoRow(t))}
      ${e.utilityStates?.map(t=>this._moreInfoRow(t))}
    `}_actionTile(e,t,i=()=>this._press(e)){let o=ht(this.hass,e);return o?this._heldActionTile(e,o,t):this._tile(e,i)}_heldActionTile(e,t,i){return p`<button class="tile"
      aria-label=${this._name(e)}
      @pointerdown=${o=>this._startHold(o,t,"up",i)}
      @pointerup=${o=>this._endPointerHold(o,t)}
      @pointercancel=${o=>this._endPointerHold(o,t)}
      @keydown=${o=>this._startHold(o,t,"up",i)}
      @keyup=${o=>this._endKeyHold(o,t)}
      @blur=${()=>this._endHold(t)}
      @click=${o=>this._activateWithoutPointer(o,t,"up",i)}
      ?disabled=${!i||!this._available(e)}>
      ${this._icon(e)}
      <span class="tile-label">${this._name(e)}</span>
    </button>`}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let l=new Set(i.map(Number));t=t.filter(g=>l.has(g.slot))}if(t.length===0)return d;let o=this._config?.memory_save!==!1&&t.some(l=>l.save),r=t.map(l=>l.save??l.goto??String(l.slot)).join("|"),a=this._saveModeFor===r;return p`
      <div class="section-heading heading-row">
        <span>${u(this.hass,"section.memory")}</span>
        ${o?p`<button
                class="set-btn ${a?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${a?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${u(this.hass,a?"memory.cancel":"memory.set")}</span>
              </button>`:d}
      </div>
      ${a?p`<div class="hint">${u(this.hass,"memory.set_hint")}</div>`:d}
      <div class="tiles">${t.map(l=>this._memoryTile(l,a,e.stop))}</div>
    `}_memoryTile(e,t,i){let o=e.goto??e.save;if(t){let a=!!e.save;return p`
        <button
          class="tile ${a?"save-mode":"is-disabled"}"
          ?disabled=${!a}
          @click=${()=>a&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(o)}</span>
        </button>
      `}let r=!!e.goto;return r?this._actionTile(e.goto,i):p`
      <button
        class="tile ${r?"":"is-disabled"}"
        ?disabled=${!r}
        @click=${()=>e.goto&&this._press(e.goto)}
      >
        ${this._icon(o)}
        <span class="tile-label">${this._name(o)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;if(!G(t)&&!t.state)return d;let o=i||t.state||t.level||t.numbers?.length||t.timer||t.toggle||t.cycle||t.timerMinutes||t.timerToggle||t.buttons?.length;return p`
      ${this._heading("section.lighting")}
      ${t.mood&&o?this._subheading("lighting.floor"):d}
      ${i?this._toggleRow(i):d}
      ${t.state?this._moreInfoRow(t.state):d}
      ${t.level?this._moreInfoRow(t.level):d}
      ${t.numbers?.map(r=>this._moreInfoRow(r))}
      ${t.timer?this._moreInfoRow(t.timer):d}
      ${t.timerMinutes?this._moreInfoRow(t.timerMinutes):d}
      ${!t.timerAppliesImmediately&&(t.timerMinutes||t.timerToggle)?p`<div class="hint">${u(this.hass,"lighting.timer_pending")}</div>`:d}
      ${t.toggle||t.cycle||t.timerToggle||t.buttons?.length?p`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):d}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):d}
              ${t.timerToggle?this._tile(t.timerToggle,()=>this._press(t.timerToggle)):d}
              ${t.buttons?.map(r=>this._actionTile(r,e.stop))}
            </div>`:d}
      ${t.mood?p`
        ${this._subheading("lighting.mood")}
        ${t.mood.selects.map(r=>this._moreInfoRow(r))}
        ${t.mood.numbers.map(r=>this._moreInfoRow(r))}
        ${t.mood.toggle||t.mood.buttons?.length?p`<div class="tiles">
          ${t.mood.toggle?this._tile(t.mood.toggle,()=>this._press(t.mood.toggle)):d}
          ${t.mood.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
        </div>`:d}
      `:d}
    `}_massage(e){let t=e.massage;return t.buttons.length===0&&t.numbers.length===0&&!t.selects?.length&&!t.states?.length&&!t.timer?d:p`
      ${this._heading("section.massage")}
      ${t.buttons.length?p`<div class="tiles">
              ${t.buttons.map(i=>this._actionTile(i,e.stop))}
            </div>`:d}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.selects?.map(i=>this._moreInfoRow(i))}
      ${t.states?.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):d}
    `}_climate(e){let t=[...e.climate.entities,...e.climate.selects,...e.climate.numbers];return t.length===0?d:p`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?d:p`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):d}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):d}
      </div>
    `}_heading(e){return p`<div class="section-heading">${u(this.hass,e)}</div>`}_subheading(e){return p`<div class="lighting-heading">${u(this.hass,e)}</div>`}_tile(e,t,i={}){return p`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${this._name(e)}</span>
      </button>
    `}_onRowKey(e,t){e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),t())}_toggleRow(e){let i=this._state(e)?.state==="on",o=this._name(e);return p`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${o}
        @click=${()=>this._moreInfo(e)}
        @keydown=${r=>this._onRowKey(r,()=>this._moreInfo(e))}
      >
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${o}</span>
          <span class="secondary">${this._stateText(e)}</span>
        </div>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${o}
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(e)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_moreInfoRow(e){let t=this._name(e);return p`
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
    `}_icon(e,t){let i=this._state(e);return i?p`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:p`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return p`<ha-card><div class="notice">${u(this.hass,e)}</div></ha-card>`}_state(e){return this.hass?.states[e]}_title(e){return this._config?.name?this._config.name:this._deviceName(e)??u(this.hass,"card.default_name")}_deviceName(e=this._config?.device_id){let t=e?this.hass?.devices[e]:void 0;return t?.name_by_user||t?.name||void 0}_name(e){let t=this._state(e)?.attributes.friendly_name??this.hass?.entities[e]?.name??e,i=this.hass?.entities[e]?.device_id,o=this._deviceName(i);return o&&t.startsWith(o+" ")?t.slice(o.length+1):t}_motorName(e){let t=`motor.${e.key}`,i=u(this.hass,t);return i!==t?i:e.key.split("_").map(o=>o.charAt(0).toUpperCase()+o.slice(1)).join(" ")}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){let t=e.angle??e.position;if(t){let i=this._angle(e);if(i===void 0)return;let o=this._state(t)?.attributes.unit_of_measurement,r=e.angle?"\xB0":"%";return`${Math.round(i)}${typeof o=="string"?o:r}`}if(e.cover){let i=this._state(e.cover)?.attributes.current_position;return typeof i=="number"?`${Math.round(i)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(o=>o&&t.add(o));e.presets.forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(o=>o&&t.add(o));return[e.stop,e.synchro,e.controlSide,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.state,e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.lights.timerMinutes,e.lights.timerToggle,e.lights.mood?.toggle,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.lights.buttons?.forEach(i=>t.add(i)),e.lights.numbers?.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.massage.selects?.forEach(i=>t.add(i)),e.massage.states?.forEach(i=>t.add(i)),e.lights.mood?.selects.forEach(i=>t.add(i)),e.lights.mood?.numbers.forEach(i=>t.add(i)),e.lights.mood?.buttons?.forEach(i=>t.add(i)),e.utility.forEach(i=>t.add(i)),e.utilityNumbers?.forEach(i=>t.add(i)),e.utilitySelects?.forEach(i=>t.add(i)),e.utilityStates?.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),e.climate.numbers.forEach(i=>t.add(i)),[...t]}_startHold(e,t,i,o){let r=null;if(e instanceof KeyboardEvent){if(e.repeat||e.key!=="Enter"&&e.key!==" ")return;e.preventDefault()}else{if(e.button!==0||!e.isPrimary)return;e.currentTarget.setPointerCapture?.(e.pointerId),e.preventDefault(),r=e.pointerId}this._config?.layout==="compact"&&(o?this._compactStopTargets.set(o,Symbol()):t.cover&&this._compactStopTargets.set(t.cover,Symbol()),this.requestUpdate()),this._hold.start(t,i,r,o)}_activateWithoutPointer(e,t,i,o){if(e.detail!==0||this._hold.heldKey!==null)return;if(this._config?.layout==="compact"&&(o?this._compactStopTargets.set(o,Symbol()):t.cover&&this._compactStopTargets.set(t.cover,Symbol()),this.requestUpdate()),t.cover){this._cover(t.cover,i==="up"?"open_cover":"close_cover");return}let r=i==="up"?t.up:t.down;r&&this._press(r)}_endPointerHold(e,t){this._hold.endFromPointer(t,e.pointerId,e.type!=="pointerup"||e.button===0)}_endKeyHold(e,t){e.key!=="Enter"&&e.key!==" "||this._hold.end(t)}_endHold(e){this._hold.end(e)}_motorStop(e,t){if(e.cover){this._hold.cancel(e,!0),this._cover(e.cover,"stop_cover");return}this._hold.stopAll(t,this._stopCoversAllTargets(t))}_stopCoversAllTargets(e){let t=e?this.hass?.states[e]?.attributes.bed_side:void 0;return t!=="left"&&t!=="right"}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_setEntities(e,t){this.hass?.callService("homeassistant",t?"turn_on":"turn_off",{entity_id:e})?.catch(()=>{})}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};C.styles=ee`
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
  `,S([q({attribute:!1})],C.prototype,"hass",2),S([B()],C.prototype,"_config",2),S([B()],C.prototype,"_saveModeFor",2),S([B()],C.prototype,"_activePairedPane",2),S([B()],C.prototype,"_synchronizingTo",2),S([B()],C.prototype,"_synchronizationFailed",2);he("adjustable-bed-card",C);console.info(`%c adjustable-bed-card %c ${bt} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{C as AdjustableBedCard};
