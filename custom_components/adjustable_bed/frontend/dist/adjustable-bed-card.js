/* adjustable-bed-card 4.0.0b5 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var Xe=Object.defineProperty;var Qe=Object.getOwnPropertyDescriptor;var _=(o,s,e,t)=>{for(var i=t>1?void 0:t?Qe(s,e):s,n=o.length-1,r;n>=0;n--)(r=o[n])&&(i=(t?r(s,e,i):r(i))||i);return t&&i&&Xe(s,e,i),i};var S="adjustable_bed";function $e(o){for(let s of["left","right","both"]){let e=`_${s}`;if(o.endsWith(e))return{key:o.slice(0,-e.length),side:s}}return{key:o}}var H=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],xe=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],oe=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_swing","preset_incline","preset_both_up","preset_yoga"],et=o=>o.split(".",1)[0],we=o=>o.translation_key??"";function tt(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[]},utility:[]}}function x(o,s,e){let t=tt();if(!s||!o?.entities)return t;let i=new Map,n=p=>{let h=i.get(p);return h||(h={key:p},i.set(p,h)),h},r=new Map,c=new Map,a=p=>{let h=c.get(p);return h||(h={slot:p},c.set(p,h)),h};for(let p of Object.values(o.entities)){if(p.device_id!==s||p.platform!==S||p.hidden)continue;let h=p.entity_id,B=et(h),se=we(p);if(!se)continue;let be=$e(se),Ze=o.states[h]?.attributes.bed_side??o.states[h]?.attributes.side??be.side;if(e&&Ze!==e)continue;let u=e?be.key:se,k;switch(B){case"cover":n(u).cover=h;break;case"sensor":u.endsWith("_angle")&&(n(u.slice(0,-6)).angle=h);break;case"number":u.endsWith("_position")?n(u.slice(0,-9)).position=h:u.startsWith("massage_")&&u.endsWith("_intensity")?t.massage.numbers.push(h):u==="light_level"?t.lights.level=h:u.startsWith("sleep_number_setting")&&t.firmness.push(h);break;case"button":oe.includes(u)||u.startsWith("preset_")?(k=u.match(/^preset_memory_(\d+)$/))?a(Number(k[1])).goto=h:r.set(u,h):(k=u.match(/^program_memory_(\d+)$/))?a(Number(k[1])).save=h:u==="stop"||u==="stop_both"?t.stop=h:u==="connect"?t.connect=h:u==="disconnect"?t.disconnect=h:u==="toggle_light"?t.lights.toggle=h:u==="light_cycle"?t.lights.cycle=h:u==="sync_positions"||u==="child_lock_toggle"||u==="auxiliary_action"||u==="solace_music_toggle"||u==="solace_music_off"||u==="wake_controller"||u==="reset_defaults"||u==="factory_reset"?t.utility.push(h):u.startsWith("massage_")?t.massage.buttons.push(h):(k=u.match(/^(.+)_(up|down)$/))&&(n(k[1])[k[2]]=h);break;case"switch":u==="under_bed_lights"?t.lights.switch=h:u==="synchro_mode"?t.synchro=h:u==="linak_automatic_drive"&&t.utility.push(h);break;case"light":t.lights.light=h;break;case"binary_sensor":u==="ble_connection"?t.connectivity=h:u.startsWith("bed_presence")&&t.presence.push(h);break;case"select":u==="light_timer"?t.lights.timer=h:u==="massage_timer"?t.massage.timer=h:/thermal|footwarming|foundation/.test(u)&&t.climate.selects.push(h);break;case"climate":t.climate.entities.push(h);break}}let g=[...i.keys()],f=[...xe.filter(p=>i.has(p)),...g.filter(p=>!xe.includes(p)).sort()];t.motors=f.map(p=>i.get(p)).filter(p=>p.cover||p.up||p.down||p.angle||p.position);let v=[...r.keys()];return t.presets=[...oe.filter(p=>r.has(p)),...v.filter(p=>!oe.includes(p)).sort()].map(p=>r.get(p)),t.memory=[...c.values()].filter(p=>p.goto||p.save).sort((p,h)=>p.slot-h.slot),t}function Ee(o,s){return!s||!o?.entities?!1:Object.values(o.entities).some(e=>e.device_id===s&&e.platform===S&&(o.states[e.entity_id]?.attributes.bed_side==="both"||$e(we(e)).side==="both"))}function ne(o,s){if(!s||!o?.devices)return[];let e=t=>{let i=o.devices[t];return(i?.name_by_user??i?.name??t).toLowerCase()};return Object.values(o.devices).filter(t=>t.via_device_id===s).map(t=>t.id).sort((t,i)=>e(t)<e(i)?-1:e(t)>e(i)?1:0)}function ke(o,s){if(!s||!o?.devices)return s;let e=o.devices[s]?.via_device_id;return e&&o.devices[e]&&ne(o,e).length?e:s}function z(o){let s=o.lights;return o.motors.length===0&&!o.synchro&&o.firmness.length===0&&o.presets.length===0&&o.memory.length===0&&!o.stop&&!o.connect&&!o.disconnect&&!o.connectivity&&!s.light&&!s.switch&&!s.level&&!s.toggle&&!s.cycle&&!s.timer&&o.massage.buttons.length===0&&o.massage.numbers.length===0&&!o.massage.timer&&o.climate.entities.length===0&&o.climate.selects.length===0&&o.utility.length===0}var re="adjustable-bed-card",Se={type:re,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(o,s)=>{let e=o.entities[s];return e?.platform!==S||!e.device_id?null:{config:{type:`custom:${re}`,device_id:e.device_id}}}};function it(o){let s=o.customCards??=[],e=s.findIndex(t=>t.type===re);e===-1?s.push(Se):s[e]=Se}typeof window<"u"&&it(window);var Y=globalThis,J=Y.ShadowRoot&&(Y.ShadyCSS===void 0||Y.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,ae=Symbol(),Ae=new WeakMap,j=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==ae)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(J&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=Ae.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&Ae.set(e,s))}return s}toString(){return this.cssText}},Pe=o=>new j(typeof o=="string"?o:o+"",void 0,ae),U=(o,...s)=>{let e=o.length===1?o[0]:s.reduce((t,i,n)=>t+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+o[n+1],o[0]);return new j(e,o,ae)},Ce=(o,s)=>{if(J)o.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=Y.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,o.appendChild(t)}},ce=J?o=>o:o=>o instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return Pe(e)})(o):o;var{is:st,defineProperty:ot,getOwnPropertyDescriptor:nt,getOwnPropertyNames:rt,getOwnPropertySymbols:at,getPrototypeOf:ct}=Object,Z=globalThis,Me=Z.trustedTypes,lt=Me?Me.emptyScript:"",dt=Z.reactiveElementPolyfillSupport,F=(o,s)=>o,G={toAttribute(o,s){switch(s){case Boolean:o=o?lt:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,s){let e=o;switch(s){case Boolean:e=o!==null;break;case Number:e=o===null?null:Number(o);break;case Object:case Array:try{e=JSON.parse(o)}catch{e=null}}return e}},X=(o,s)=>!st(o,s),Re={attribute:!0,type:String,converter:G,reflect:!1,useDefault:!1,hasChanged:X};Symbol.metadata??=Symbol("metadata"),Z.litPropertyMetadata??=new WeakMap;var $=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=Re){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&ot(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:n}=nt(this.prototype,s)??{get(){return this[e]},set(r){this[e]=r}};return{get:i,set(r){let c=i?.call(this);n?.call(this,r),this.requestUpdate(s,c,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??Re}static _$Ei(){if(this.hasOwnProperty(F("elementProperties")))return;let s=ct(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(F("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(F("properties"))){let e=this.properties,t=[...rt(e),...at(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(ce(i))}else s!==void 0&&e.push(ce(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Ce(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let n=(t.converter?.toAttribute!==void 0?t.converter:G).toAttribute(e,t.type);this._$Em=s,n==null?this.removeAttribute(i):this.setAttribute(i,n),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let n=t.getPropertyOptions(i),r=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:G;this._$Em=i;let c=r.fromAttribute(e,n.type);this[i]=c??this._$Ej?.get(i)??c,this._$Em=null}}requestUpdate(s,e,t,i=!1,n){if(s!==void 0){let r=this.constructor;if(i===!1&&(n=this[s]),t??=r.getPropertyOptions(s),!((t.hasChanged??X)(n,e)||t.useDefault&&t.reflect&&n===this._$Ej?.get(s)&&!this.hasAttribute(r._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:n},r){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,r??e??this[s]),n!==!0||r!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,n]of this._$Ep)this[i]=n;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,n]of t){let{wrapped:r}=n,c=this[i];r!==!0||this._$AL.has(i)||c===void 0||this.C(i,void 0,n,c)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};$.elementStyles=[],$.shadowRootOptions={mode:"open"},$[F("elementProperties")]=new Map,$[F("finalized")]=new Map,dt?.({ReactiveElement:$}),(Z.reactiveElementVersions??=[]).push("2.1.2");var me=globalThis,Te=o=>o,Q=me.trustedTypes,Be=Q?Q.createPolicy("lit-html",{createHTML:o=>o}):void 0,Le="$lit$",w=`lit$${Math.random().toFixed(9).slice(2)}$`,je="?"+w,ht=`<${je}>`,C=document,K=()=>C.createComment(""),W=o=>o===null||typeof o!="object"&&typeof o!="function",fe=Array.isArray,pt=o=>fe(o)||typeof o?.[Symbol.iterator]=="function",le=`[ \t
\f\r]`,I=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,He=/-->/g,ze=/>/g,A=RegExp(`>|${le}(?:([^\\s"'>=/]+)(${le}*=${le}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),Oe=/'/g,De=/"/g,Ue=/^(?:script|style|textarea|title)$/i,ve=o=>(s,...e)=>({_$litType$:o,strings:s,values:e}),d=ve(1),ee=ve(2),Ht=ve(3),M=Symbol.for("lit-noChange"),l=Symbol.for("lit-nothing"),Ne=new WeakMap,P=C.createTreeWalker(C,129);function Fe(o,s){if(!fe(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return Be!==void 0?Be.createHTML(s):s}var ut=(o,s)=>{let e=o.length-1,t=[],i,n=s===2?"<svg>":s===3?"<math>":"",r=I;for(let c=0;c<e;c++){let a=o[c],g,f,v=-1,p=0;for(;p<a.length&&(r.lastIndex=p,f=r.exec(a),f!==null);)p=r.lastIndex,r===I?f[1]==="!--"?r=He:f[1]!==void 0?r=ze:f[2]!==void 0?(Ue.test(f[2])&&(i=RegExp("</"+f[2],"g")),r=A):f[3]!==void 0&&(r=A):r===A?f[0]===">"?(r=i??I,v=-1):f[1]===void 0?v=-2:(v=r.lastIndex-f[2].length,g=f[1],r=f[3]===void 0?A:f[3]==='"'?De:Oe):r===De||r===Oe?r=A:r===He||r===ze?r=I:(r=A,i=void 0);let h=r===A&&o[c+1].startsWith("/>")?" ":"";n+=r===I?a+ht:v>=0?(t.push(g),a.slice(0,v)+Le+a.slice(v)+w+h):a+w+(v===-2?c:h)}return[Fe(o,n+(o[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},q=class o{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let n=0,r=0,c=s.length-1,a=this.parts,[g,f]=ut(s,e);if(this.el=o.createElement(g,t),P.currentNode=this.el.content,e===2||e===3){let v=this.el.content.firstChild;v.replaceWith(...v.childNodes)}for(;(i=P.nextNode())!==null&&a.length<c;){if(i.nodeType===1){if(i.hasAttributes())for(let v of i.getAttributeNames())if(v.endsWith(Le)){let p=f[r++],h=i.getAttribute(v).split(w),B=/([.?@])?(.*)/.exec(p);a.push({type:1,index:n,name:B[2],strings:h,ctor:B[1]==="."?he:B[1]==="?"?pe:B[1]==="@"?ue:D}),i.removeAttribute(v)}else v.startsWith(w)&&(a.push({type:6,index:n}),i.removeAttribute(v));if(Ue.test(i.tagName)){let v=i.textContent.split(w),p=v.length-1;if(p>0){i.textContent=Q?Q.emptyScript:"";for(let h=0;h<p;h++)i.append(v[h],K()),P.nextNode(),a.push({type:2,index:++n});i.append(v[p],K())}}}else if(i.nodeType===8)if(i.data===je)a.push({type:2,index:n});else{let v=-1;for(;(v=i.data.indexOf(w,v+1))!==-1;)a.push({type:7,index:n}),v+=w.length-1}n++}}static createElement(s,e){let t=C.createElement("template");return t.innerHTML=s,t}};function O(o,s,e=o,t){if(s===M)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,n=W(s)?void 0:s._$litDirective$;return i?.constructor!==n&&(i?._$AO?.(!1),n===void 0?i=void 0:(i=new n(o),i._$AT(o,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=O(o,i._$AS(o,s.values),i,t)),s}var de=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??C).importNode(e,!0);P.currentNode=i;let n=P.nextNode(),r=0,c=0,a=t[0];for(;a!==void 0;){if(r===a.index){let g;a.type===2?g=new V(n,n.nextSibling,this,s):a.type===1?g=new a.ctor(n,a.name,a.strings,this,s):a.type===6&&(g=new ge(n,this,s)),this._$AV.push(g),a=t[++c]}r!==a?.index&&(n=P.nextNode(),r++)}return P.currentNode=C,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},V=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=l,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=O(this,s,e),W(s)?s===l||s==null||s===""?(this._$AH!==l&&this._$AR(),this._$AH=l):s!==this._$AH&&s!==M&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):pt(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==l&&W(this._$AH)?this._$AA.nextSibling.data=s:this.T(C.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=q.createElement(Fe(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let n=new de(i,this),r=n.u(this.options);n.p(e),this.T(r),this._$AH=n}}_$AC(s){let e=Ne.get(s.strings);return e===void 0&&Ne.set(s.strings,e=new q(s)),e}k(s){fe(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let n of s)i===e.length?e.push(t=new o(this.O(K()),this.O(K()),this,this.options)):t=e[i],t._$AI(n),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=Te(s).nextSibling;Te(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},D=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,n){this.type=1,this._$AH=l,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=n,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=l}_$AI(s,e=this,t,i){let n=this.strings,r=!1;if(n===void 0)s=O(this,s,e,0),r=!W(s)||s!==this._$AH&&s!==M,r&&(this._$AH=s);else{let c=s,a,g;for(s=n[0],a=0;a<n.length-1;a++)g=O(this,c[t+a],e,a),g===M&&(g=this._$AH[a]),r||=!W(g)||g!==this._$AH[a],g===l?s=l:s!==l&&(s+=(g??"")+n[a+1]),this._$AH[a]=g}r&&!i&&this.j(s)}j(s){s===l?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},he=class extends D{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===l?void 0:s}},pe=class extends D{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==l)}},ue=class extends D{constructor(s,e,t,i,n){super(s,e,t,i,n),this.type=5}_$AI(s,e=this){if((s=O(this,s,e,0)??l)===M)return;let t=this._$AH,i=s===l&&t!==l||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,n=s!==l&&(t===l||i);i&&this.element.removeEventListener(this.name,this,t),n&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},ge=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){O(this,s)}};var gt=me.litHtmlPolyfillSupport;gt?.(q,V),(me.litHtmlVersions??=[]).push("3.3.3");var Ge=(o,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let n=e?.renderBefore??null;t._$litPart$=i=new V(s.insertBefore(K(),n),n,void 0,e??{})}return i._$AI(o),i};var _e=globalThis,y=class extends ${constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=Ge(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return M}};y._$litElement$=!0,y.finalized=!0,_e.litElementHydrateSupport?.({LitElement:y});var mt=_e.litElementPolyfillSupport;mt?.({LitElement:y});(_e.litElementVersions??=[]).push("4.2.2");var ft={attribute:!0,type:String,converter:G,reflect:!1,hasChanged:X},vt=(o=ft,s,e)=>{let{kind:t,metadata:i}=e,n=globalThis.litPropertyMetadata.get(i);if(n===void 0&&globalThis.litPropertyMetadata.set(i,n=new Map),t==="setter"&&((o=Object.create(o)).wrapped=!0),n.set(e.name,o),t==="accessor"){let{name:r}=e;return{set(c){let a=s.get.call(this);s.set.call(this,c),this.requestUpdate(r,a,o,!0,c)},init(c){return c!==void 0&&this.C(r,void 0,o,c),c}}}if(t==="setter"){let{name:r}=e;return function(c){let a=this[r];s.call(this,c),this.requestUpdate(r,a,o,!0,c)}}throw Error("Unsupported decorator location: "+t)};function N(o){return(s,e)=>typeof e=="object"?vt(o,s,e):((t,i,n)=>{let r=i.hasOwnProperty(n);return i.constructor.createProperty(n,t),r?Object.getOwnPropertyDescriptor(i,n):void 0})(o,s,e)}function E(o){return N({...o,state:!0,attribute:!1})}var R=o=>Math.max(0,Math.min(75,o));function Ie(o,s="theme"){let e=R(o.upper.angle??0),t=R(o.lower.angle??0),i=`rotate(${e} 150 70)`,n=`rotate(${-t} 150 70)`,r=c=>c.angle===void 0?"":`${c.label?`${c.label} `:""}${Math.round(R(c.angle))}\xB0`;return ee`
    <svg
      class="bed-graphic bed-graphic-${s} ${o.moving?"is-moving":""}"
      viewBox="0 0 300 116"
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
        <g class="bed-panel" transform=${n}>
          <rect class="bed-surface" x="150" y="58" width="108" height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel" transform=${i}>
          <rect class="bed-surface" x="42" y="58" width="108" height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
      </g>

      <text x="86" y="22" text-anchor="middle" class="bed-graphic-label">${r(o.upper)}</text>
      <text x="214" y="22" text-anchor="middle" class="bed-graphic-label">${r(o.lower)}</text>
    </svg>
  `}function Ke(o){let s=R(o.left.upper.angle??0),e=R(o.left.lower.angle??0),t=R(o.right.upper.angle??0),i=R(o.right.lower.angle??0),n=(r,c,a,g)=>ee`
    <g
      class="dual-bed-side dual-bed-side-${r} ${g?"is-moving":""}"
      fill=${`url(#abDual${r==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel"
        transform=${`rotate(${-a} 150 70)`}
      >
        <rect class="dual-bed-surface" x="150" y="58" width="108" height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel"
        transform=${`rotate(${c} 150 70)`}
      >
        <rect class="dual-bed-surface" x="42" y="58" width="108" height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
    </g>
  `;return ee`
    <svg
      class="bed-graphic dual-bed-graphic ${o.left.moving||o.right.moving?"is-moving":""}"
      viewBox="0 0 300 116"
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
      ${n("right",t,i,o.right.moving)}
      ${n("left",s,e,o.left.moving)}
    </svg>
  `}function ye(o){let s=o.find(t=>t.key==="back"||t.key==="head"),e=o.find(t=>t.key==="legs"||t.key==="feet");return s&&e?{upper:s,lower:e}:void 0}function We(o,s){let e=o.motors.filter(t=>{let i=t.angle??t.position;return s.states[i??""]?.attributes.unit_of_measurement==="\xB0"});return ye(e)!==void 0}var ie=class{constructor(s){this.actions=s;this._key=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0}get heldKey(){return this._key}start(s,e,t,i){this._key===null&&(this._key=s.key,this._cover=s.cover??null,this._stop=i??null,this._pointerId=t,this._repeat(s,e,++this._generation))}async _repeat(s,e,t){for(;t===this._generation;)try{let i=this.actions.pulse(s,e);if(!i)return;await i}catch{return}}endFromPointer(s,e,t){this._pointerId!==null&&e!==this._pointerId||t&&this.end(s)}end(s){let e=this._stop??void 0;if(this.cancel(s)){if(s.cover){this.actions.stopCover(s.cover);return}this.actions.stopBed(e)}}cancel(s){return!s||this._key!==s.key?!1:(this._reset(),!0)}stopAll(s){let e=s??this._stop??void 0;this._reset(),this.actions.stopBed(e)}abandon(){let s=this._cover,e=this._stop??void 0,t=this._key!==null;this._reset(),t&&(s?this.actions.stopCover(s):this.actions.stopBed(e))}_reset(){this._key=null,this._cover=null,this._stop=null,this._pointerId=null,this._generation++}};var qe={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized."};var Ve={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres."};var T={en:qe,nb:Ve};function bt(o){let s=(o?.locale?.language||o?.language||"en").toLowerCase(),e=s.split("-")[0];return T[s]?T[s]:T[e]?T[e]:e==="nn"||e==="no"?T.nb:T.en}function m(o,s,e){let i=bt(o)[s]??T.en[s]??s;if(e)for(let[n,r]of Object.entries(e))i=i.replace(`{${n}}`,r);return i}var Ye="4.0.0b5";function Je(o,s){return{graphic:We(o,s),motors:o.motors.some(e=>e.cover||e.up||e.down)||!!o.stop||!!o.synchro,firmness:o.firmness.length>0,presets:o.presets.length>0,memory:o.memory.length>0,lighting:!!(o.lights.light||o.lights.switch||o.lights.level||o.lights.toggle||o.lights.cycle||o.lights.timer),massage:o.massage.buttons.length>0||o.massage.numbers.length>0||!!o.massage.timer,utility:o.utility.length>0,climate:o.climate.entities.length>0||o.climate.selects.length>0,connection:!!(o.connect||o.disconnect)}}var xt="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",$t="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",wt=(o,s)=>o.length===s.length&&o.every((e,t)=>e===s[t]),L=class extends y{constructor(){super(...arguments);this._computeLabel=e=>m(this.hass,`editor.${e.name}`)}setConfig(e){this._config=e}_bed(){let e=this._config?.device_id;if(!(!this.hass||!e))return x(this.hass,e)}_presentKeys(e){let t=Je(e,this.hass);return H.filter(i=>t[i])}_orderedKeys(e){let t=this._presentKeys(e),n=(this._config?.section_order??[]).filter(c=>t.includes(c)),r=t.filter(c=>!n.includes(c));return[...n,...r]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=t&&this.hass?.states[t]?.attributes.friendly_name||`Memory ${e.slot}`,n=this._config?.device_id?this.hass?.devices[this._config.device_id]:void 0,r=n?.name_by_user||n?.name;return r&&i.startsWith(`${r} `)?i.slice(r.length+1):i}_emit(e){e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;i.device_id=t.device_id||void 0,t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let n=this._orderedKeys(e),r=n.indexOf(t),c=r+i;if(r<0||c<0||c>=n.length)return;[n[r],n[c]]=[n[c],n[r]];let a=this._cfg;wt(n,this._presentKeys(e))?delete a.section_order:a.section_order=n,this._emit(a)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let n=this._memorySlots(e),r=this._config?.memory_slots,c=r&&r.length?r.map(Number):[...n];i?c.includes(t)||c.push(t):c=c.filter(g=>g!==t),c.sort((g,f)=>g-f);let a=this._cfg;c.length===n.length?delete a.memory_slots:a.memory_slots=c,this._emit(a)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?d`
      <div class="group">
        <div class="group-title">${m(this.hass,"editor.sections")}</div>
        ${t.map((i,n)=>{let r=this._config?.[`show_${i}`]!==!1;return d`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${n===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${m(this.hass,"editor.move_up")}
                  aria-label=${m(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${xt}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${n===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${m(this.hass,"editor.move_down")}
                  aria-label=${m(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${$t}></path></svg>
                </button>
              </div>
              <span class="label">${m(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${r}
                @change=${c=>this._toggleSection(i,c.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:l}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return l;let i=e.memory.some(r=>r.save),n=e.memory.length>1;return!i&&!n?l:d`
      <div class="group">
        <div class="group-title">
          ${m(this.hass,"editor.memory_group")}
        </div>
        ${i?d`<div class="row">
                <span class="label">${m(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                ></ha-switch>
              </div>`:l}
        ${n?d`<div class="sub">
                <div class="sub-label">
                  ${m(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(r=>d`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${c=>this._toggleSlot(e,r.slot,c.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(r)}</span>
                    </label>
                  `)}
              </div>`:l}
      </div>
    `}render(){if(!this.hass||!this._config)return l;let e=this._bed();return d`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${e?this._sectionsGroup(e):l}
      ${e?this._memoryGroup(e):l}
    `}};L.styles=U`
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
  `,_([N({attribute:!1})],L.prototype,"hass",2),_([E()],L.prototype,"_config",2);customElements.get("adjustable-bed-card-editor")||customElements.define("adjustable-bed-card-editor",L);var Et=new Set(["back","legs","head","feet"]),b=class extends y{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._watched=[];this._hold=new ie({pulse:(e,t)=>{if(e.cover)return this.hass?.callService("cover",t==="up"?"open_cover":"close_cover",{entity_id:e.cover});let i=t==="up"?e.up:e.down;return i?this.hass?.callService("button","press",{entity_id:i}):void 0},stopCover:e=>this._cover(e,"stop_cover"),stopBed:e=>{e&&this._press(e)}})}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===S)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 8}disconnectedCallback(){super.disconnectedCallback(),this._hold.abandon()}shouldUpdate(e){if(e.has("_config")||e.has("_saveModeFor")||e.has("_activePairedPane")||e.has("_synchronizingTo")||e.has("_synchronizationFailed")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices)return!0;for(let i of this._watched)if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return l;if(!this._config.device_id)return this._notice("card.no_device");let e=ke(this.hass,this._config.device_id),t=ne(this.hass,e);if(e&&t.length)return this._renderPaired(e,t);if(this._config.device_id&&Ee(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=x(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),z(i)?this._notice("card.no_entities"):d`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(e,t="theme"){let i=this._config,n={graphic:()=>i.show_graphic!==!1?this._graphic(e,t):l,motors:()=>i.show_motors!==!1?this._motors(e):l,firmness:()=>i.show_firmness!==!1?this._firmness(e):l,presets:()=>i.show_presets!==!1?this._presets(e):l,memory:()=>i.show_memory!==!1?this._memory(e):l,lighting:()=>i.show_lighting!==!1?this._lighting(e):l,massage:()=>i.show_massage!==!1?this._massage(e):l,utility:()=>i.show_utility!==!1?this._utility(e):l,climate:()=>i.show_climate!==!1?this._climate(e):l,connection:()=>i.show_connection!==!1?this._connection(e):l};return this._orderedSections().map(r=>n[r]?.()??l)}_renderPaired(e,t){let i=this.hass,n=x(i,e),r=t.map((c,a)=>({key:c,label:this._deviceLabel(c),icon:"mdi:bed-single-outline",bed:x(i,c),graphicTone:a===0?"left":"right",synchronizationTarget:{deviceId:c}}));return this._watched=[n,...r.map(c=>c.bed)].flatMap(c=>this._collectWatched(c)),z(n)&&r.every(c=>z(c.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:m(i,"card.both_sides"),icon:"mdi:link-variant",bed:n},...r])}_renderSingleAddressPaired(e){let t=this.hass,i={both:x(t,e,"both"),left:x(t,e,"left"),right:x(t,e,"right")};return this._watched=Object.values(i).flatMap(n=>this._collectWatched(n)),Object.values(i).every(n=>z(n))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:m(t,"card.both_sides"),icon:"mdi:link-variant",bed:i.both},{key:"left",label:m(t,"card.left_side"),icon:"mdi:bed-single-outline",bed:i.left,graphicTone:"left",synchronizationTarget:{deviceId:e,side:"left"}},{key:"right",label:m(t,"card.right_side"),icon:"mdi:bed-single-outline",bed:i.right,graphicTone:"right",synchronizationTarget:{deviceId:e,side:"right"}}])}_renderPairedCard(e,t){let i=t.filter(a=>!z(a.bed)),n=i.find(a=>a.key===this._activePairedPane)??i[0],r=i.filter(a=>a.key!=="both"),c=n.key==="both";return d`
      <ha-card class="paired-card">
        ${this._header(n.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(a=>d`
              <button
                class="pane-tab ${a.key===n.key?"active":""}"
                role="tab"
                aria-selected=${a.key===n.key?"true":"false"}
                @click=${()=>this._selectPairedPane(a.key)}
              >
                <ha-icon icon=${a.icon}></ha-icon>
                <span>${a.label}</span>
                ${this._connectionDot(a.bed)}
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${n.label}>
          ${c&&this._config?.show_graphic!==!1?this._pairedOverview(r):l}
          ${this._renderSections(n.bed,n.graphicTone)}
          ${c&&this._config?.show_lighting!==!1?this._combinedLighting(n.bed,r):l}
          ${c&&this._config?.show_connection!==!1?this._combinedBluetooth(r):l}
        </div>
      </ha-card>
    `}_selectPairedPane(e){this._activePairedPane!==e&&(this._activePairedPane=e,this._saveModeFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(e){if(!e.connectivity)return;let t=this._state(e.connectivity);return t?.attributes?.state_detail==="connecting"?"connecting":t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(e){let t=this._connectionStatus(e);return t?d`<span
      class="connection-dot ${t}"
      title=${m(this.hass,`status.${t}`)}
    ></span>`:l}_pairedOverview(e){let t=e.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(t.length<2)return l;let[i,n]=t;return d`
      <div class="graphic dual-graphic">
        ${Ke({left:i.graphic,right:n.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,n].map(({pane:r,graphic:c},a)=>d`
            <div class="dual-readout side-${a===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${r.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(c)}
              </span>
            </div>
          `)}
      </div>
      ${this._synchronizeSelector(i.pane,n.pane)}
    `}_synchronizeSelector(e,t){if(!e.synchronizationTarget||!t.synchronizationTarget)return l;let i=this._synchronizationPlan(e.bed,t.bed),n=this._synchronizationPlan(t.bed,e.bed);if(i.length===0&&n.length===0)return l;let r=this._synchronizingTo!==void 0;return d`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${m(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${m(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"left")}
          >
            ${this._synchronizingTo==="left"?d`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:d`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${m(this.hass,"sync.label")} ${t.label}"
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
            <span>${m(this.hass,"sync.incomplete")}</span>
          </div>`:l}
    `}_synchronizationPlan(e,t){let i=new Map(t.motors.map(c=>[c.key,c])),n=e.motors.filter(c=>Et.has(c.key)&&i.has(c.key)&&this._hasPositionFeedback(c)&&this._hasPositionFeedback(i.get(c.key)));if(n.length===0)return[];let r=n.map(c=>({motor:c.key,position:this._angle(c)}));return r.some(c=>c.position===void 0)||n.some(c=>this._angle(i.get(c.key))===void 0)?[]:r}_hasPositionFeedback(e){return e.angle!==void 0||e.position!==void 0}async _synchronizePositions(e,t,i){if(this._synchronizingTo||!this.hass)return;let n=i==="left"?e:t,r=i==="left"?t:e,c=r.synchronizationTarget;if(!c)return;let a=this._synchronizationPlan(n.bed,r.bed);if(a.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(S,"set_positions",{device_id:[c.deviceId],positions:a,...c.side?{side:c.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(e){return(e.upperMotor===e.lowerMotor?[e.upperMotor]:[e.upperMotor,e.lowerMotor]).map(i=>{let n=this._readout(i);return n?`${this._motorName(i)} ${n}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(e,t){if(this._hasLighting(e))return l;let i=t.map(f=>this._mainLight(f.bed)).filter(f=>f!==void 0);if(i.length===0)return l;let n=i.filter(f=>this._state(f)?.state==="on").length,r=n===i.length,c=n>0,a=r?"combined.on":c?"combined.mixed":"combined.off",g=m(this.hass,"combined.lights");return d`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${c?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${g}</span>
          <span class="secondary">${m(this.hass,a)}</span>
        </div>
        <button
          class="toggle ${c?"on":""} ${c&&!r?"mixed":""}"
          role="switch"
          aria-label=${g}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(e){let t=e.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return t.length===0?l:d`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${t.map(({pane:i,entityId:n})=>{let r=this._connectionStatus(i.bed),a=this._state(n)?.attributes.rssi;return d`
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
                  ${m(this.hass,`status.${r}`)}${typeof a=="number"?` \xB7 ${a} dBm`:""}
                </span>
              </span>
            </button>
          `})}
      </div>
    `}_mainLight(e){return e.lights.light??e.lights.switch}_hasLighting(e){let t=e.lights;return!!(t.light||t.switch||t.level||t.timer||t.toggle||t.cycle)}_deviceLabel(e){let t=this.hass?.devices[e];return t?.name_by_user??t?.name??e}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...H];let t=new Set(H),i=e.filter(r=>t.has(r)),n=H.filter(r=>!i.includes(r));return[...i,...n]}_header(e,t){let i=this._connectionStatus(e),n={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return d`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${i===void 0?l:d`
                <button
                  class="conn ${n[i].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${m(this.hass,n[i].key)}
                >
                  <ha-icon icon=${n[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e,t="theme"){let i=this._graphicState(e);return i?d`
      <div class="graphic">
        ${Ie(i,t)}
      </div>
    `:l}_graphicState(e){let t=e.motors.filter(a=>{let g=a.angle??a.position;return g!==void 0&&this._state(g)?.attributes.unit_of_measurement==="\xB0"});if(t.length===0||t.some(a=>this._angle(a)===void 0))return;let i=ye(t);if(!i)return;let{upper:n,lower:r}=i,c=e.motors.some(a=>{let g=a.cover?this._state(a.cover)?.state:void 0;return g==="opening"||g==="closing"});return{upperMotor:n,lowerMotor:r,upper:{label:this._motorName(n),angle:this._angle(n)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:c}}_motors(e){let t=e.motors.filter(r=>r.cover||r.up||r.down),i=e.motors.filter(r=>r.position);if(t.length===0&&i.length===0&&!e.synchro&&!e.stop)return l;let n=t.length>0||i.length>0||!!e.synchro;return d`
      ${n?this._heading("section.position"):l}
      ${e.synchro?this._toggleRow(e.synchro):l}
      ${t.length?d`<div class="rows">
              ${t.map(r=>this._motorRow(r,e.stop))}
            </div>`:l}
      ${i.length?d`<div class="rows">
              ${i.map(r=>this._moreInfoRow(r.position))}
            </div>`:l}
      ${e.stop?d`<button class="stop-all" @click=${()=>this._hold.stopAll(e.stop)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${m(this.hass,"action.stop_all")}</span>
            </button>`:l}
    `}_firmness(e){return e.firmness.length===0?l:d`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t){let i=this._readout(e),n=e.cover??e.up,r=e.cover??e.down,c=!!e.cover||!!t;return d`
      <div class="row">
        <div class="row-label">
          <span>${this._motorName(e)}</span>
          ${i?d`<span class="readout">${i}</span>`:l}
        </div>
        <div class="control-group">
          <button
            class="cg-btn"
            aria-label=${m(this.hass,"action.up")}
            @pointerdown=${a=>this._startHold(a,e,"up",t)}
            @pointerup=${a=>this._endPointerHold(a,e)}
            @pointercancel=${a=>this._endPointerHold(a,e)}
            @keydown=${a=>this._startHold(a,e,"up",t)}
            @keyup=${a=>this._endKeyHold(a,e)}
            @blur=${()=>this._endHold(e)}
            @click=${a=>this._activateWithoutPointer(a,e,"up")}
            ?disabled=${!n}
          >
            <ha-icon icon="mdi:chevron-up"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${m(this.hass,"action.stop")}
            @click=${()=>this._motorStop(e,t)}
            ?disabled=${!c}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${m(this.hass,"action.down")}
            @pointerdown=${a=>this._startHold(a,e,"down",t)}
            @pointerup=${a=>this._endPointerHold(a,e)}
            @pointercancel=${a=>this._endPointerHold(a,e)}
            @keydown=${a=>this._startHold(a,e,"down",t)}
            @keyup=${a=>this._endKeyHold(a,e)}
            @blur=${()=>this._endHold(e)}
            @click=${a=>this._activateWithoutPointer(a,e,"down")}
            ?disabled=${!r}
          >
            <ha-icon icon="mdi:chevron-down"></ha-icon>
          </button>
        </div>
      </div>
    `}_presets(e){return e.presets.length===0?l:d`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._tile(t,()=>this._press(t)))}
      </div>
    `}_utility(e){return e.utility.length===0?l:d`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${e.utility.map(t=>this._tile(t,()=>t.startsWith("switch.")?this._call("switch","toggle",t):this._press(t)))}
      </div>
    `}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let a=new Set(i.map(Number));t=t.filter(g=>a.has(g.slot))}if(t.length===0)return l;let n=this._config?.memory_save!==!1&&t.some(a=>a.save),r=t.map(a=>a.save??a.goto??String(a.slot)).join("|"),c=this._saveModeFor===r;return d`
      <div class="section-heading heading-row">
        <span>${m(this.hass,"section.memory")}</span>
        ${n?d`<button
                class="set-btn ${c?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${c?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${m(this.hass,c?"memory.cancel":"memory.set")}</span>
              </button>`:l}
      </div>
      ${c?d`<div class="hint">${m(this.hass,"memory.set_hint")}</div>`:l}
      <div class="tiles">${t.map(a=>this._memoryTile(a,c))}</div>
    `}_memoryTile(e,t){let i=e.goto??e.save;if(t){let r=!!e.save;return d`
        <button
          class="tile ${r?"save-mode":"is-disabled"}"
          ?disabled=${!r}
          @click=${()=>r&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(i)}</span>
        </button>
      `}let n=!!e.goto;return d`
      <button
        class="tile ${n?"":"is-disabled"}"
        ?disabled=${!n}
        @click=${()=>e.goto&&this._press(e.goto)}
      >
        ${this._icon(i)}
        <span class="tile-label">${this._name(i)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;return!i&&!t.level&&!t.timer&&!t.toggle&&!t.cycle?l:d`
      ${this._heading("section.lighting")}
      ${i?this._toggleRow(i):l}
      ${t.level?this._moreInfoRow(t.level):l}
      ${t.timer?this._moreInfoRow(t.timer):l}
      ${t.toggle||t.cycle?d`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):l}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):l}
            </div>`:l}
    `}_massage(e){let t=e.massage;return t.buttons.length===0&&t.numbers.length===0&&!t.timer?l:d`
      ${this._heading("section.massage")}
      ${t.buttons.length?d`<div class="tiles">
              ${t.buttons.map(i=>this._tile(i,()=>this._press(i)))}
            </div>`:l}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):l}
    `}_climate(e){let t=[...e.climate.entities,...e.climate.selects];return t.length===0?l:d`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?l:d`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):l}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):l}
      </div>
    `}_heading(e){return d`<div class="section-heading">${m(this.hass,e)}</div>`}_tile(e,t,i={}){return d`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${this._name(e)}</span>
      </button>
    `}_onRowKey(e,t){e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),t())}_toggleRow(e){let i=this._state(e)?.state==="on",n=this._name(e);return d`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${n}
        @click=${()=>this._moreInfo(e)}
        @keydown=${r=>this._onRowKey(r,()=>this._moreInfo(e))}
      >
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${n}</span>
          <span class="secondary">${this._stateText(e)}</span>
        </div>
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
    `}_moreInfoRow(e){let t=this._name(e);return d`
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
      ></ha-state-icon>`:d`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return d`<ha-card><div class="notice">${m(this.hass,e)}</div></ha-card>`}_state(e){return this.hass?.states[e]}_title(e){return this._config?.name?this._config.name:this._deviceName(e)??m(this.hass,"card.default_name")}_deviceName(e=this._config?.device_id){let t=e?this.hass?.devices[e]:void 0;return t?.name_by_user||t?.name||void 0}_name(e){let t=this._state(e)?.attributes.friendly_name??this.hass?.entities[e]?.name??e,i=this.hass?.entities[e]?.device_id,n=this._deviceName(i);return n&&t.startsWith(n+" ")?t.slice(n.length+1):t}_motorName(e){let t=`motor.${e.key}`,i=m(this.hass,t);return i!==t?i:e.key.split("_").map(n=>n.charAt(0).toUpperCase()+n.slice(1)).join(" ")}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){let t=e.angle??e.position;if(t){let i=this._angle(e);if(i===void 0)return;let n=this._state(t)?.attributes.unit_of_measurement,r=e.angle?"\xB0":"%";return`${Math.round(i)}${typeof n=="string"?n:r}`}if(e.cover){let i=this._state(e.cover)?.attributes.current_position;return typeof i=="number"?`${Math.round(i)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(n=>n&&t.add(n));e.presets.forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(n=>n&&t.add(n));return[e.stop,e.synchro,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.utility.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),[...t]}_startHold(e,t,i,n){let r=null;if(e instanceof KeyboardEvent){if(e.repeat||e.key!=="Enter"&&e.key!==" ")return;e.preventDefault()}else{if(e.button!==0||!e.isPrimary)return;e.currentTarget.setPointerCapture?.(e.pointerId),e.preventDefault(),r=e.pointerId}this._hold.start(t,i,r,n)}_activateWithoutPointer(e,t,i){if(e.detail!==0||this._hold.heldKey!==null)return;if(t.cover){this._cover(t.cover,i==="up"?"open_cover":"close_cover");return}let n=i==="up"?t.up:t.down;n&&this._press(n)}_endPointerHold(e,t){this._hold.endFromPointer(t,e.pointerId,e.type!=="pointerup"||e.button===0)}_endKeyHold(e,t){e.key!=="Enter"&&e.key!==" "||this._hold.end(t)}_endHold(e){this._hold.end(e)}_motorStop(e,t){if(e.cover){this._hold.cancel(e),this._cover(e.cover,"stop_cover");return}this._hold.stopAll(t)}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_setEntities(e,t){this.hass?.callService("homeassistant",t?"turn_on":"turn_off",{entity_id:e})?.catch(()=>{})}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};b.styles=U`
    :host {
      --ab-gap: 10px;
      --ab-side-left-rgb: 75, 0, 255;
      --ab-side-right-rgb: 234, 65, 65;
    }
    ha-card {
      padding: 12px 12px 16px;
      overflow: hidden;
    }
    .header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 4px 8px;
    }
    .header-icon {
      color: var(--state-icon-color, var(--primary-text-color));
      --mdc-icon-size: 22px;
    }
    .title {
      font-size: 1.1rem;
      font-weight: 500;
      color: var(--primary-text-color);
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .conn {
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
    .pane-tabs {
      display: grid;
      grid-template-columns: repeat(var(--pane-count, 3), minmax(0, 1fr));
      gap: 4px;
      padding: 4px;
      margin: 0 0 6px;
      border-radius: 14px;
      background: var(--secondary-background-color);
    }
    .pane-tab {
      min-width: 0;
      height: 42px;
      padding: 0 8px;
      border: 0;
      border-radius: 11px;
      background: transparent;
      color: var(--secondary-text-color);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      font: inherit;
      font-size: 0.82rem;
      font-weight: 500;
      transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
      -webkit-user-select: none;
      user-select: none;
      touch-action: manipulation;
    }
    .pane-tab ha-icon {
      --mdc-icon-size: 19px;
      flex: none;
    }
    .pane-tab span:not(.connection-dot) {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pane-tab:hover {
      color: var(--primary-text-color);
    }
    .pane-tab.active {
      color: var(--primary-text-color);
      background: var(--card-background-color);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.14);
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
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
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
      animation: ab-pulse 2s ease-in-out infinite;
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
      opacity: 0.78;
      stroke: var(--primary-text-color);
      stroke-opacity: 0.14;
      stroke-width: 1px;
      vector-effect: non-scaling-stroke;
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
      stroke-opacity: 0.1;
      stroke-width: 1px;
      vector-effect: non-scaling-stroke;
    }
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
      animation: ab-side-pulse 1.4s ease-in-out infinite;
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
      border-radius: 10px;
      background: var(--secondary-background-color);
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
      border: 1px solid var(--divider-color);
      border-radius: 11px;
      background: var(--card-background-color);
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
      border: 1px solid var(--divider-color);
      border-radius: 9px;
      background: var(--secondary-background-color);
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
      animation: ab-spin 0.8s linear infinite;
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
    @keyframes ab-spin {
      to {
        transform: rotate(360deg);
      }
    }
    @keyframes ab-pulse {
      0%,
      100% {
        filter: drop-shadow(0 0 3px rgba(var(--ab-graphic-rgb), 0.25));
      }
      50% {
        filter: drop-shadow(0 0 10px rgba(var(--ab-graphic-rgb), 0.55));
      }
    }
    @keyframes ab-side-pulse {
      0%,
      100% {
        opacity: 0.58;
      }
      50% {
        opacity: 0.88;
      }
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
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      padding: 8px 12px;
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
    .control-group {
      display: inline-flex;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--divider-color);
    }
    .cg-btn {
      border: none;
      background: var(--card-background-color);
      color: var(--primary-color);
      cursor: pointer;
      padding: 8px 14px;
      display: inline-flex;
      align-items: center;
      --mdc-icon-size: 22px;
      transition: background 0.15s ease;
      /* Press-and-hold has to survive a slightly unsteady finger. Pointer
         capture and preventDefault() do not override the browser's touch
         gesture arbitration, so without this a small vertical drag starts
         scrolling the page, fires pointercancel and cuts the hold short. */
      touch-action: none;
    }
    .cg-btn:not(:last-child) {
      border-right: 1px solid var(--divider-color);
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
      border-radius: 12px;
      cursor: pointer;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
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
      gap: 6px;
      padding: 14px 6px 10px;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
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
      --mdc-icon-size: 24px;
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
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
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
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      background: var(--card-background-color);
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
  `,_([N({attribute:!1})],b.prototype,"hass",2),_([E()],b.prototype,"_config",2),_([E()],b.prototype,"_saveModeFor",2),_([E()],b.prototype,"_activePairedPane",2),_([E()],b.prototype,"_synchronizingTo",2),_([E()],b.prototype,"_synchronizationFailed",2);customElements.get("adjustable-bed-card")||customElements.define("adjustable-bed-card",b);console.info(`%c adjustable-bed-card %c ${Ye} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{b as AdjustableBedCard};
