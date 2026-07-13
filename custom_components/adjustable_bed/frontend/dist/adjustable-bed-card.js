/* adjustable-bed-card 4.0.0b0 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var Ve=Object.defineProperty;var Je=Object.getOwnPropertyDescriptor;var _=(o,s,e,t)=>{for(var i=t>1?void 0:t?Je(s,e):s,r=o.length-1,n;r>=0;r--)(n=o[r])&&(i=(t?n(s,e,i):n(i))||i);return t&&i&&Ve(s,e,i),i};var V=globalThis,J=V.ShadowRoot&&(V.ShadyCSS===void 0||V.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,oe=Symbol(),ye=new WeakMap,j=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==oe)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(J&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=ye.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&ye.set(e,s))}return s}toString(){return this.cssText}},$e=o=>new j(typeof o=="string"?o:o+"",void 0,oe),U=(o,...s)=>{let e=o.length===1?o[0]:s.reduce((t,i,r)=>t+(n=>{if(n._$cssResult$===!0)return n.cssText;if(typeof n=="number")return n;throw Error("Value passed to 'css' function must be a 'css' function result: "+n+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+o[r+1],o[0]);return new j(e,o,oe)},xe=(o,s)=>{if(J)o.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=V.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,o.appendChild(t)}},re=J?o=>o:o=>o instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return $e(e)})(o):o;var{is:Ye,defineProperty:Xe,getOwnPropertyDescriptor:Ze,getOwnPropertyNames:Qe,getOwnPropertySymbols:et,getPrototypeOf:tt}=Object,Y=globalThis,we=Y.trustedTypes,it=we?we.emptyScript:"",st=Y.reactiveElementPolyfillSupport,z=(o,s)=>o,G={toAttribute(o,s){switch(s){case Boolean:o=o?it:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,s){let e=o;switch(s){case Boolean:e=o!==null;break;case Number:e=o===null?null:Number(o);break;case Object:case Array:try{e=JSON.parse(o)}catch{e=null}}return e}},X=(o,s)=>!Ye(o,s),Ee={attribute:!0,type:String,converter:G,reflect:!1,useDefault:!1,hasChanged:X};Symbol.metadata??=Symbol("metadata"),Y.litPropertyMetadata??=new WeakMap;var y=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=Ee){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&Xe(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:r}=Ze(this.prototype,s)??{get(){return this[e]},set(n){this[e]=n}};return{get:i,set(n){let a=i?.call(this);r?.call(this,n),this.requestUpdate(s,a,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??Ee}static _$Ei(){if(this.hasOwnProperty(z("elementProperties")))return;let s=tt(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(z("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(z("properties"))){let e=this.properties,t=[...Qe(e),...et(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(re(i))}else s!==void 0&&e.push(re(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return xe(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let r=(t.converter?.toAttribute!==void 0?t.converter:G).toAttribute(e,t.type);this._$Em=s,r==null?this.removeAttribute(i):this.setAttribute(i,r),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let r=t.getPropertyOptions(i),n=typeof r.converter=="function"?{fromAttribute:r.converter}:r.converter?.fromAttribute!==void 0?r.converter:G;this._$Em=i;let a=n.fromAttribute(e,r.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(s,e,t,i=!1,r){if(s!==void 0){let n=this.constructor;if(i===!1&&(r=this[s]),t??=n.getPropertyOptions(s),!((t.hasChanged??X)(r,e)||t.useDefault&&t.reflect&&r===this._$Ej?.get(s)&&!this.hasAttribute(n._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:r},n){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,n??e??this[s]),r!==!0||n!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,r]of this._$Ep)this[i]=r;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,r]of t){let{wrapped:n}=r,a=this[i];n!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,r,a)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};y.elementStyles=[],y.shadowRootOptions={mode:"open"},y[z("elementProperties")]=new Map,y[z("finalized")]=new Map,st?.({ReactiveElement:y}),(Y.reactiveElementVersions??=[]).push("2.1.2");var pe=globalThis,Se=o=>o,Z=pe.trustedTypes,ke=Z?Z.createPolicy("lit-html",{createHTML:o=>o}):void 0,Te="$lit$",w=`lit$${Math.random().toFixed(9).slice(2)}$`,Be="?"+w,ot=`<${Be}>`,A=document,I=()=>A.createComment(""),K=o=>o===null||typeof o!="object"&&typeof o!="function",ge=Array.isArray,rt=o=>ge(o)||typeof o?.[Symbol.iterator]=="function",ne=`[ 	
\f\r]`,F=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Ae=/-->/g,Re=/>/g,S=RegExp(`>|${ne}(?:([^\\s"'>=/]+)(${ne}*=${ne}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Ce=/'/g,Me=/"/g,Oe=/^(?:script|style|textarea|title)$/i,ue=o=>(s,...e)=>({_$litType$:o,strings:s,values:e}),h=ue(1),Q=ue(2),kt=ue(3),R=Symbol.for("lit-noChange"),l=Symbol.for("lit-nothing"),Pe=new WeakMap,k=A.createTreeWalker(A,129);function He(o,s){if(!ge(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return ke!==void 0?ke.createHTML(s):s}var nt=(o,s)=>{let e=o.length-1,t=[],i,r=s===2?"<svg>":s===3?"<math>":"",n=F;for(let a=0;a<e;a++){let c=o[a],u,f,v=-1,p=0;for(;p<c.length&&(n.lastIndex=p,f=n.exec(c),f!==null);)p=n.lastIndex,n===F?f[1]==="!--"?n=Ae:f[1]!==void 0?n=Re:f[2]!==void 0?(Oe.test(f[2])&&(i=RegExp("</"+f[2],"g")),n=S):f[3]!==void 0&&(n=S):n===S?f[0]===">"?(n=i??F,v=-1):f[1]===void 0?v=-2:(v=n.lastIndex-f[2].length,u=f[1],n=f[3]===void 0?S:f[3]==='"'?Me:Ce):n===Me||n===Ce?n=S:n===Ae||n===Re?n=F:(n=S,i=void 0);let d=n===S&&o[a+1].startsWith("/>")?" ":"";r+=n===F?c+ot:v>=0?(t.push(u),c.slice(0,v)+Te+c.slice(v)+w+d):c+w+(v===-2?a:d)}return[He(o,r+(o[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},W=class o{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let r=0,n=0,a=s.length-1,c=this.parts,[u,f]=nt(s,e);if(this.el=o.createElement(u,t),k.currentNode=this.el.content,e===2||e===3){let v=this.el.content.firstChild;v.replaceWith(...v.childNodes)}for(;(i=k.nextNode())!==null&&c.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let v of i.getAttributeNames())if(v.endsWith(Te)){let p=f[n++],d=i.getAttribute(v).split(w),T=/([.?@])?(.*)/.exec(p);c.push({type:1,index:r,name:T[2],strings:d,ctor:T[1]==="."?ce:T[1]==="?"?le:T[1]==="@"?de:O}),i.removeAttribute(v)}else v.startsWith(w)&&(c.push({type:6,index:r}),i.removeAttribute(v));if(Oe.test(i.tagName)){let v=i.textContent.split(w),p=v.length-1;if(p>0){i.textContent=Z?Z.emptyScript:"";for(let d=0;d<p;d++)i.append(v[d],I()),k.nextNode(),c.push({type:2,index:++r});i.append(v[p],I())}}}else if(i.nodeType===8)if(i.data===Be)c.push({type:2,index:r});else{let v=-1;for(;(v=i.data.indexOf(w,v+1))!==-1;)c.push({type:7,index:r}),v+=w.length-1}r++}}static createElement(s,e){let t=A.createElement("template");return t.innerHTML=s,t}};function B(o,s,e=o,t){if(s===R)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,r=K(s)?void 0:s._$litDirective$;return i?.constructor!==r&&(i?._$AO?.(!1),r===void 0?i=void 0:(i=new r(o),i._$AT(o,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=B(o,i._$AS(o,s.values),i,t)),s}var ae=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??A).importNode(e,!0);k.currentNode=i;let r=k.nextNode(),n=0,a=0,c=t[0];for(;c!==void 0;){if(n===c.index){let u;c.type===2?u=new q(r,r.nextSibling,this,s):c.type===1?u=new c.ctor(r,c.name,c.strings,this,s):c.type===6&&(u=new he(r,this,s)),this._$AV.push(u),c=t[++a]}n!==c?.index&&(r=k.nextNode(),n++)}return k.currentNode=A,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},q=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=l,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=B(this,s,e),K(s)?s===l||s==null||s===""?(this._$AH!==l&&this._$AR(),this._$AH=l):s!==this._$AH&&s!==R&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):rt(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==l&&K(this._$AH)?this._$AA.nextSibling.data=s:this.T(A.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=W.createElement(He(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let r=new ae(i,this),n=r.u(this.options);r.p(e),this.T(n),this._$AH=r}}_$AC(s){let e=Pe.get(s.strings);return e===void 0&&Pe.set(s.strings,e=new W(s)),e}k(s){ge(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let r of s)i===e.length?e.push(t=new o(this.O(I()),this.O(I()),this,this.options)):t=e[i],t._$AI(r),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=Se(s).nextSibling;Se(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},O=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,r){this.type=1,this._$AH=l,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=r,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=l}_$AI(s,e=this,t,i){let r=this.strings,n=!1;if(r===void 0)s=B(this,s,e,0),n=!K(s)||s!==this._$AH&&s!==R,n&&(this._$AH=s);else{let a=s,c,u;for(s=r[0],c=0;c<r.length-1;c++)u=B(this,a[t+c],e,c),u===R&&(u=this._$AH[c]),n||=!K(u)||u!==this._$AH[c],u===l?s=l:s!==l&&(s+=(u??"")+r[c+1]),this._$AH[c]=u}n&&!i&&this.j(s)}j(s){s===l?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},ce=class extends O{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===l?void 0:s}},le=class extends O{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==l)}},de=class extends O{constructor(s,e,t,i,r){super(s,e,t,i,r),this.type=5}_$AI(s,e=this){if((s=B(this,s,e,0)??l)===R)return;let t=this._$AH,i=s===l&&t!==l||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,r=s!==l&&(t===l||i);i&&this.element.removeEventListener(this.name,this,t),r&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},he=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){B(this,s)}};var at=pe.litHtmlPolyfillSupport;at?.(W,q),(pe.litHtmlVersions??=[]).push("3.3.3");var Ne=(o,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let r=e?.renderBefore??null;t._$litPart$=i=new q(s.insertBefore(I(),r),r,void 0,e??{})}return i._$AI(o),i};var me=globalThis,b=class extends y{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=Ne(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return R}};b._$litElement$=!0,b.finalized=!0,me.litElementHydrateSupport?.({LitElement:b});var ct=me.litElementPolyfillSupport;ct?.({LitElement:b});(me.litElementVersions??=[]).push("4.2.2");var ee=o=>(s,e)=>{e!==void 0?e.addInitializer(()=>{customElements.define(o,s)}):customElements.define(o,s)};var lt={attribute:!0,type:String,converter:G,reflect:!1,hasChanged:X},dt=(o=lt,s,e)=>{let{kind:t,metadata:i}=e,r=globalThis.litPropertyMetadata.get(i);if(r===void 0&&globalThis.litPropertyMetadata.set(i,r=new Map),t==="setter"&&((o=Object.create(o)).wrapped=!0),r.set(e.name,o),t==="accessor"){let{name:n}=e;return{set(a){let c=s.get.call(this);s.set.call(this,a),this.requestUpdate(n,c,o,!0,a)},init(a){return a!==void 0&&this.C(n,void 0,o,a),a}}}if(t==="setter"){let{name:n}=e;return function(a){let c=this[n];s.call(this,a),this.requestUpdate(n,c,o,!0,a)}}throw Error("Unsupported decorator location: "+t)};function H(o){return(s,e)=>typeof e=="object"?dt(o,s,e):((t,i,r)=>{let n=i.hasOwnProperty(r);return i.constructor.createProperty(r,t),n?Object.getOwnPropertyDescriptor(i,r):void 0})(o,s,e)}function N(o){return H({...o,state:!0,attribute:!1})}var C=o=>Math.max(0,Math.min(75,o));function Le(o,s="theme"){let e=C(o.upper.angle??0),t=C(o.lower.angle??0),i=`rotate(${e} 150 70)`,r=`rotate(${-t} 150 70)`,n=a=>a.angle===void 0?"":`${a.label?`${a.label} `:""}${Math.round(C(a.angle))}\xB0`;return Q`
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
        <g class="bed-panel" transform=${r}>
          <rect class="bed-surface" x="150" y="58" width="108" height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel" transform=${i}>
          <rect class="bed-surface" x="42" y="58" width="108" height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
      </g>

      <text x="86" y="22" text-anchor="middle" class="bed-graphic-label">${n(o.upper)}</text>
      <text x="214" y="22" text-anchor="middle" class="bed-graphic-label">${n(o.lower)}</text>
    </svg>
  `}function De(o){let s=C(o.left.upper.angle??0),e=C(o.left.lower.angle??0),t=C(o.right.upper.angle??0),i=C(o.right.lower.angle??0),r=(n,a,c,u)=>Q`
    <g
      class="dual-bed-side dual-bed-side-${n} ${u?"is-moving":""}"
      fill=${`url(#abDual${n==="left"?"Left":"Right"})`}
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
  `;return Q`
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
      ${r("right",t,i,o.right.moving)}
      ${r("left",s,e,o.left.moving)}
    </svg>
  `}var ie="adjustable_bed";function Ue(o){for(let s of["left","right","both"]){let e=`_${s}`;if(o.endsWith(e))return{key:o.slice(0,-e.length),side:s}}return{key:o}}var L=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],je=["back","legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],fe=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_incline","preset_both_up","preset_yoga"],ht=o=>o.split(".",1)[0],ze=o=>o.translation_key??"";function pt(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[]},utility:[]}}function $(o,s,e){let t=pt();if(!s||!o?.entities)return t;let i=new Map,r=p=>{let d=i.get(p);return d||(d={key:p},i.set(p,d)),d},n=new Map,a=new Map,c=p=>{let d=a.get(p);return d||(d={slot:p},a.set(p,d)),d};for(let p of Object.values(o.entities)){if(p.device_id!==s||p.platform!==ie||p.hidden)continue;let d=p.entity_id,T=ht(d),se=ze(p);if(!se)continue;let be=Ue(se),qe=o.states[d]?.attributes.bed_side??o.states[d]?.attributes.side??be.side;if(e&&qe!==e)continue;let m=e?be.key:se,E;switch(T){case"cover":r(m).cover=d;break;case"sensor":m.endsWith("_angle")&&(r(m.slice(0,-6)).angle=d);break;case"number":m.endsWith("_position")?r(m.slice(0,-9)).position=d:m.startsWith("massage_")&&m.endsWith("_intensity")?t.massage.numbers.push(d):m==="light_level"?t.lights.level=d:m.startsWith("sleep_number_setting")&&t.firmness.push(d);break;case"button":fe.includes(m)||m.startsWith("preset_")?(E=m.match(/^preset_memory_(\d+)$/))?c(Number(E[1])).goto=d:n.set(m,d):(E=m.match(/^program_memory_(\d+)$/))?c(Number(E[1])).save=d:m==="stop"||m==="stop_both"?t.stop=d:m==="connect"?t.connect=d:m==="disconnect"?t.disconnect=d:m==="toggle_light"?t.lights.toggle=d:m==="light_cycle"?t.lights.cycle=d:m==="sync_positions"||m==="child_lock_toggle"?t.utility.push(d):m.startsWith("massage_")?t.massage.buttons.push(d):(E=m.match(/^(.+)_(up|down)$/))&&(r(E[1])[E[2]]=d);break;case"switch":m==="under_bed_lights"?t.lights.switch=d:m==="synchro_mode"&&(t.synchro=d);break;case"light":t.lights.light=d;break;case"binary_sensor":m==="ble_connection"?t.connectivity=d:m.startsWith("bed_presence")&&t.presence.push(d);break;case"select":m==="light_timer"?t.lights.timer=d:m==="massage_timer"?t.massage.timer=d:/thermal|footwarming|foundation/.test(m)&&t.climate.selects.push(d);break;case"climate":t.climate.entities.push(d);break}}let u=[...i.keys()],f=[...je.filter(p=>i.has(p)),...u.filter(p=>!je.includes(p)).sort()];t.motors=f.map(p=>i.get(p)).filter(p=>p.cover||p.up||p.down||p.angle||p.position);let v=[...n.keys()];return t.presets=[...fe.filter(p=>n.has(p)),...v.filter(p=>!fe.includes(p)).sort()].map(p=>n.get(p)),t.memory=[...a.values()].filter(p=>p.goto||p.save).sort((p,d)=>p.slot-d.slot),t}function Ge(o,s){return!s||!o?.entities?!1:Object.values(o.entities).some(e=>e.device_id===s&&e.platform===ie&&(o.states[e.entity_id]?.attributes.bed_side==="both"||Ue(ze(e)).side==="both"))}function ve(o,s){if(!s||!o?.devices)return[];let e=t=>{let i=o.devices[t];return(i?.name_by_user??i?.name??t).toLowerCase()};return Object.values(o.devices).filter(t=>t.via_device_id===s).map(t=>t.id).sort((t,i)=>e(t)<e(i)?-1:e(t)>e(i)?1:0)}function Fe(o,s){if(!s||!o?.devices)return s;let e=o.devices[s]?.via_device_id;return e&&o.devices[e]&&ve(o,e).length?e:s}function D(o){let s=o.lights;return o.motors.length===0&&!o.synchro&&o.firmness.length===0&&o.presets.length===0&&o.memory.length===0&&!o.stop&&!o.connect&&!o.disconnect&&!o.connectivity&&!s.light&&!s.switch&&!s.level&&!s.toggle&&!s.cycle&&!s.timer&&o.massage.buttons.length===0&&o.massage.numbers.length===0&&!o.massage.timer&&o.climate.entities.length===0&&o.climate.selects.length===0&&o.utility.length===0}var Ie={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on"};var Ke={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5"};var M={en:Ie,nb:Ke};function mt(o){let s=(o?.locale?.language||o?.language||"en").toLowerCase(),e=s.split("-")[0];return M[s]?M[s]:M[e]?M[e]:e==="nn"||e==="no"?M.nb:M.en}function g(o,s,e){let i=mt(o)[s]??M.en[s]??s;if(e)for(let[r,n]of Object.entries(e))i=i.replace(`{${r}}`,n);return i}var We="4.0.0b0";var ft="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",vt="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z";function _t(o){return{graphic:o.motors.some(s=>s.angle),motors:o.motors.some(s=>s.cover||s.up||s.down)||!!o.stop||!!o.synchro,firmness:o.firmness.length>0,presets:o.presets.length>0,memory:o.memory.length>0,lighting:!!(o.lights.light||o.lights.switch||o.lights.level||o.lights.toggle||o.lights.cycle||o.lights.timer),massage:o.massage.buttons.length>0||o.massage.numbers.length>0||!!o.massage.timer,climate:o.climate.entities.length>0||o.climate.selects.length>0,connection:!!(o.connect||o.disconnect)}}var bt=(o,s)=>o.length===s.length&&o.every((e,t)=>e===s[t]),P=class extends b{constructor(){super(...arguments);this._computeLabel=e=>g(this.hass,`editor.${e.name}`)}setConfig(e){this._config=e}_bed(){let e=this._config?.device_id;if(!(!this.hass||!e))return $(this.hass,e)}_presentKeys(e){let t=_t(e);return L.filter(i=>t[i])}_orderedKeys(e){let t=this._presentKeys(e),r=(this._config?.section_order??[]).filter(a=>t.includes(a)),n=t.filter(a=>!r.includes(a));return[...r,...n]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=t&&this.hass?.states[t]?.attributes.friendly_name||`Memory ${e.slot}`,r=this._config?.device_id?this.hass?.devices[this._config.device_id]:void 0,n=r?.name_by_user||r?.name;return n&&i.startsWith(`${n} `)?i.slice(n.length+1):i}_emit(e){e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;i.device_id=t.device_id||void 0,t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let r=this._orderedKeys(e),n=r.indexOf(t),a=n+i;if(n<0||a<0||a>=r.length)return;[r[n],r[a]]=[r[a],r[n]];let c=this._cfg;bt(r,this._presentKeys(e))?delete c.section_order:c.section_order=r,this._emit(c)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let r=this._memorySlots(e),n=this._config?.memory_slots,a=n&&n.length?n.map(Number):[...r];i?a.includes(t)||a.push(t):a=a.filter(u=>u!==t),a.sort((u,f)=>u-f);let c=this._cfg;a.length===r.length?delete c.memory_slots:c.memory_slots=a,this._emit(c)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?h`
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.sections")}</div>
        ${t.map((i,r)=>{let n=this._config?.[`show_${i}`]!==!1;return h`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${r===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${g(this.hass,"editor.move_up")}
                  aria-label=${g(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${ft}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${r===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${g(this.hass,"editor.move_down")}
                  aria-label=${g(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${vt}></path></svg>
                </button>
              </div>
              <span class="label">${g(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${n}
                @change=${a=>this._toggleSection(i,a.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:l}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return l;let i=e.memory.some(n=>n.save),r=e.memory.length>1;return!i&&!r?l:h`
      <div class="group">
        <div class="group-title">
          ${g(this.hass,"editor.memory_group")}
        </div>
        ${i?h`<div class="row">
                <span class="label">${g(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${n=>this._setMemorySave(n.target.checked)}
                ></ha-switch>
              </div>`:l}
        ${r?h`<div class="sub">
                <div class="sub-label">
                  ${g(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(n=>h`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(n.slot)}
                        @change=${a=>this._toggleSlot(e,n.slot,a.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(n)}</span>
                    </label>
                  `)}
              </div>`:l}
      </div>
    `}render(){if(!this.hass||!this._config)return l;let e=this._bed();return h`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${e?this._sectionsGroup(e):l}
      ${e?this._memoryGroup(e):l}
    `}};P.styles=U`
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
  `,_([H({attribute:!1})],P.prototype,"hass",2),_([N()],P.prototype,"_config",2),P=_([ee("adjustable-bed-card-editor")],P);var x=class extends b{constructor(){super(...arguments);this._activePairedPane="both";this._watched=[]}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===ie)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 8}shouldUpdate(e){if(e.has("_config")||e.has("_saveModeFor")||e.has("_activePairedPane")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices)return!0;for(let i of this._watched)if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return l;if(!this._config.device_id)return this._notice("card.no_device");let e=Fe(this.hass,this._config.device_id),t=ve(this.hass,e);if(e&&t.length)return this._renderPaired(e,t);if(this._config.device_id&&Ge(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=$(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),D(i)?this._notice("card.no_entities"):h`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(e,t="theme"){let i=this._config,r={graphic:()=>i.show_graphic!==!1?this._graphic(e,t):l,motors:()=>i.show_motors!==!1?this._motors(e):l,firmness:()=>i.show_firmness!==!1?this._firmness(e):l,presets:()=>i.show_presets!==!1?this._presets(e):l,memory:()=>i.show_memory!==!1?this._memory(e):l,lighting:()=>i.show_lighting!==!1?this._lighting(e):l,massage:()=>i.show_massage!==!1?this._massage(e):l,utility:()=>i.show_utility!==!1?this._utility(e):l,climate:()=>i.show_climate!==!1?this._climate(e):l,connection:()=>i.show_connection!==!1?this._connection(e):l};return this._orderedSections().map(n=>r[n]?.()??l)}_renderPaired(e,t){let i=this.hass,r=$(i,e),n=t.map((a,c)=>({key:a,label:this._deviceLabel(a),icon:"mdi:bed-single-outline",bed:$(i,a),graphicTone:c===0?"left":"right"}));return this._watched=[r,...n.map(a=>a.bed)].flatMap(a=>this._collectWatched(a)),D(r)&&n.every(a=>D(a.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:g(i,"card.both_sides"),icon:"mdi:link-variant",bed:r},...n])}_renderSingleAddressPaired(e){let t=this.hass,i={both:$(t,e,"both"),left:$(t,e,"left"),right:$(t,e,"right")};return this._watched=Object.values(i).flatMap(r=>this._collectWatched(r)),Object.values(i).every(r=>D(r))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:g(t,"card.both_sides"),icon:"mdi:link-variant",bed:i.both},{key:"left",label:g(t,"card.left_side"),icon:"mdi:bed-single-outline",bed:i.left,graphicTone:"left"},{key:"right",label:g(t,"card.right_side"),icon:"mdi:bed-single-outline",bed:i.right,graphicTone:"right"}])}_renderPairedCard(e,t){let i=t.filter(c=>!D(c.bed)),r=i.find(c=>c.key===this._activePairedPane)??i[0],n=i.filter(c=>c.key!=="both"),a=r.key==="both";return h`
      <ha-card class="paired-card">
        ${this._header(r.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(c=>h`
              <button
                class="pane-tab ${c.key===r.key?"active":""}"
                role="tab"
                aria-selected=${c.key===r.key?"true":"false"}
                @click=${()=>this._selectPairedPane(c.key)}
              >
                <ha-icon icon=${c.icon}></ha-icon>
                <span>${c.label}</span>
                ${this._connectionDot(c.bed)}
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${r.label}>
          ${a&&this._config?.show_graphic!==!1?this._pairedOverview(n):l}
          ${this._renderSections(r.bed,r.graphicTone)}
          ${a&&this._config?.show_lighting!==!1?this._combinedLighting(r.bed,n):l}
          ${a&&this._config?.show_connection!==!1?this._combinedBluetooth(n):l}
        </div>
      </ha-card>
    `}_selectPairedPane(e){this._activePairedPane!==e&&(this._activePairedPane=e,this._saveModeFor=void 0)}_connectionStatus(e){if(!e.connectivity)return;let t=this._state(e.connectivity);return t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(e){let t=this._connectionStatus(e);return t?h`<span
      class="connection-dot ${t}"
      title=${g(this.hass,`status.${t}`)}
    ></span>`:l}_pairedOverview(e){let t=e.map(n=>({pane:n,graphic:this._graphicState(n.bed)})).filter(n=>n.graphic!==void 0);if(t.length<2)return l;let[i,r]=t;return h`
      <div class="graphic dual-graphic">
        ${De({left:i.graphic,right:r.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,r].map(({pane:n,graphic:a},c)=>h`
            <div class="dual-readout side-${c===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${n.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(a)}
              </span>
            </div>
          `)}
      </div>
    `}_positionSummary(e){return(e.upperMotor===e.lowerMotor?[e.upperMotor]:[e.upperMotor,e.lowerMotor]).map(i=>{let r=this._readout(i);return r?`${this._motorName(i)} ${r}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(e,t){if(this._hasLighting(e))return l;let i=t.map(f=>this._mainLight(f.bed)).filter(f=>f!==void 0);if(i.length===0)return l;let r=i.filter(f=>this._state(f)?.state==="on").length,n=r===i.length,a=r>0,c=n?"combined.on":a?"combined.mixed":"combined.off",u=g(this.hass,"combined.lights");return h`
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
          class="toggle ${a?"on":""} ${a&&!n?"mixed":""}"
          role="switch"
          aria-label=${u}
          aria-checked=${n?"true":"false"}
          @click=${()=>this._setEntities(i,!n)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(e){let t=e.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return t.length===0?l:h`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${t.map(({pane:i,entityId:r})=>{let n=this._connectionStatus(i.bed),c=this._state(r)?.attributes.rssi;return h`
            <button
              class="bluetooth-status ${n}"
              @click=${()=>this._moreInfo(r)}
            >
              <ha-icon
                icon=${n==="connected"?"mdi:bluetooth-connect":n==="idle"?"mdi:bluetooth":"mdi:bluetooth-off"}
              ></ha-icon>
              <span class="bluetooth-copy">
                <span>${i.label}</span>
                <span class="bluetooth-detail">
                  ${g(this.hass,`status.${n}`)}${typeof c=="number"?` \xB7 ${c} dBm`:""}
                </span>
              </span>
            </button>
          `})}
      </div>
    `}_mainLight(e){return e.lights.light??e.lights.switch}_hasLighting(e){let t=e.lights;return!!(t.light||t.switch||t.level||t.timer||t.toggle||t.cycle)}_deviceLabel(e){let t=this.hass?.devices[e];return t?.name_by_user??t?.name??e}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...L];let t=new Set(L),i=e.filter(n=>t.has(n)),r=L.filter(n=>!i.includes(n));return[...i,...r]}_header(e,t){let i=this._connectionStatus(e),r={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return h`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${i===void 0?l:h`
                <button
                  class="conn ${r[i].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${g(this.hass,r[i].key)}
                >
                  <ha-icon icon=${r[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e,t="theme"){let i=this._graphicState(e);return i?h`
      <div class="graphic">
        ${Le(i,t)}
      </div>
    `:l}_graphicState(e){let t=e.motors.filter(a=>a.angle);if(t.length===0)return;let i=e.motors.find(a=>a.key==="back")??e.motors.find(a=>a.key==="head")??t[0],r=e.motors.find(a=>a.key==="legs")??e.motors.find(a=>a.key==="feet")??t[t.length-1],n=e.motors.some(a=>{let c=a.cover?this._state(a.cover)?.state:void 0;return c==="opening"||c==="closing"});return{upperMotor:i,lowerMotor:r,upper:{label:this._motorName(i),angle:this._angle(i)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:n}}_motors(e){let t=e.motors.filter(n=>n.cover||n.up||n.down),i=e.motors.filter(n=>!n.cover&&!n.up&&!n.down&&n.position);if(t.length===0&&i.length===0&&!e.synchro&&!e.stop)return l;let r=t.length>0||i.length>0||!!e.synchro;return h`
      ${r?this._heading("section.position"):l}
      ${e.synchro?this._toggleRow(e.synchro):l}
      ${t.length?h`<div class="rows">
              ${t.map(n=>this._motorRow(n,e.stop))}
            </div>`:l}
      ${i.length?h`<div class="rows">
              ${i.map(n=>this._moreInfoRow(n.position))}
            </div>`:l}
      ${e.stop?h`<button class="stop-all" @click=${()=>this._press(e.stop)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${g(this.hass,"action.stop_all")}</span>
            </button>`:l}
    `}_firmness(e){return e.firmness.length===0?l:h`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t){let i=this._readout(e),r=e.cover??e.up,n=e.cover??e.down,a=!!e.cover||!!t;return h`
      <div class="row">
        <div class="row-label">
          <span>${this._motorName(e)}</span>
          ${i?h`<span class="readout">${i}</span>`:l}
        </div>
        <div class="control-group">
          <button
            class="cg-btn"
            aria-label=${g(this.hass,"action.up")}
            @click=${()=>this._motorAction(e,"up")}
            ?disabled=${!r}
          >
            <ha-icon icon="mdi:chevron-up"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${g(this.hass,"action.stop")}
            @click=${()=>this._motorStop(e,t)}
            ?disabled=${!a}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${g(this.hass,"action.down")}
            @click=${()=>this._motorAction(e,"down")}
            ?disabled=${!n}
          >
            <ha-icon icon="mdi:chevron-down"></ha-icon>
          </button>
        </div>
      </div>
    `}_presets(e){return e.presets.length===0?l:h`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._tile(t,()=>this._press(t)))}
      </div>
    `}_utility(e){return e.utility.length===0?l:h`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${e.utility.map(t=>this._tile(t,()=>this._press(t)))}
      </div>
    `}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let c=new Set(i.map(Number));t=t.filter(u=>c.has(u.slot))}if(t.length===0)return l;let r=this._config?.memory_save!==!1&&t.some(c=>c.save),n=t.map(c=>c.save??c.goto??String(c.slot)).join("|"),a=this._saveModeFor===n;return h`
      <div class="section-heading heading-row">
        <span>${g(this.hass,"section.memory")}</span>
        ${r?h`<button
                class="set-btn ${a?"active":""}"
                @click=${()=>this._toggleSaveMode(n)}
              >
                <ha-icon
                  icon=${a?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${g(this.hass,a?"memory.cancel":"memory.set")}</span>
              </button>`:l}
      </div>
      ${a?h`<div class="hint">${g(this.hass,"memory.set_hint")}</div>`:l}
      <div class="tiles">${t.map(c=>this._memoryTile(c,a))}</div>
    `}_memoryTile(e,t){let i=e.goto??e.save;if(t){let n=!!e.save;return h`
        <button
          class="tile ${n?"save-mode":"is-disabled"}"
          ?disabled=${!n}
          @click=${()=>n&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(i)}</span>
        </button>
      `}let r=!!e.goto;return h`
      <button
        class="tile ${r?"":"is-disabled"}"
        ?disabled=${!r}
        @click=${()=>e.goto&&this._press(e.goto)}
      >
        ${this._icon(i)}
        <span class="tile-label">${this._name(i)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;return!i&&!t.level&&!t.timer&&!t.toggle&&!t.cycle?l:h`
      ${this._heading("section.lighting")}
      ${i?this._toggleRow(i):l}
      ${t.level?this._moreInfoRow(t.level):l}
      ${t.timer?this._moreInfoRow(t.timer):l}
      ${t.toggle||t.cycle?h`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):l}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):l}
            </div>`:l}
    `}_massage(e){let t=e.massage;return t.buttons.length===0&&t.numbers.length===0&&!t.timer?l:h`
      ${this._heading("section.massage")}
      ${t.buttons.length?h`<div class="tiles">
              ${t.buttons.map(i=>this._tile(i,()=>this._press(i)))}
            </div>`:l}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):l}
    `}_climate(e){let t=[...e.climate.entities,...e.climate.selects];return t.length===0?l:h`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?l:h`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):l}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):l}
      </div>
    `}_heading(e){return h`<div class="section-heading">${g(this.hass,e)}</div>`}_tile(e,t,i={}){return h`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${this._name(e)}</span>
      </button>
    `}_onRowKey(e,t){e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),t())}_toggleRow(e){let i=this._state(e)?.state==="on",r=this._name(e);return h`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${r}
        @click=${()=>this._moreInfo(e)}
        @keydown=${n=>this._onRowKey(n,()=>this._moreInfo(e))}
      >
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${r}</span>
          <span class="secondary">${this._stateText(e)}</span>
        </div>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${r}
          aria-checked=${i?"true":"false"}
          @click=${n=>{n.stopPropagation(),this._toggle(e)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_moreInfoRow(e){let t=this._name(e);return h`
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
    `}_icon(e,t){let i=this._state(e);return i?h`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:h`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return h`<ha-card><div class="notice">${g(this.hass,e)}</div></ha-card>`}_state(e){return this.hass?.states[e]}_title(e){return this._config?.name?this._config.name:this._deviceName(e)??g(this.hass,"card.default_name")}_deviceName(e=this._config?.device_id){let t=e?this.hass?.devices[e]:void 0;return t?.name_by_user||t?.name||void 0}_name(e){let t=this._state(e)?.attributes.friendly_name??this.hass?.entities[e]?.name??e,i=this.hass?.entities[e]?.device_id,r=this._deviceName(i);return r&&t.startsWith(r+" ")?t.slice(r.length+1):t}_motorName(e){let t=`motor.${e.key}`,i=g(this.hass,t);return i!==t?i:e.key.split("_").map(r=>r.charAt(0).toUpperCase()+r.slice(1)).join(" ")}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){if(e.angle){let t=this._angle(e);return t===void 0?void 0:`${Math.round(t)}\xB0`}if(e.position){let t=this._angle(e);return t===void 0?void 0:`${Math.round(t)}%`}if(e.cover){let t=this._state(e.cover)?.attributes.current_position;return typeof t=="number"?`${Math.round(t)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(r=>r&&t.add(r));e.presets.forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(r=>r&&t.add(r));return[e.stop,e.synchro,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),[...t]}_motorAction(e,t){if(e.cover)this._cover(e.cover,t==="up"?"open_cover":"close_cover");else{let i=t==="up"?e.up:e.down;i&&this._press(i)}}_motorStop(e,t){e.cover?this._cover(e.cover,"stop_cover"):t&&this._press(t)}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_setEntities(e,t){this.hass?.callService("homeassistant",t?"turn_on":"turn_off",{entity_id:e})?.catch(()=>{})}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};x.styles=U`
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
  `,_([H({attribute:!1})],x.prototype,"hass",2),_([N()],x.prototype,"_config",2),_([N()],x.prototype,"_saveModeFor",2),_([N()],x.prototype,"_activePairedPane",2),x=_([ee("adjustable-bed-card")],x);var _e=window;_e.customCards=_e.customCards||[];_e.customCards.push({type:"adjustable-bed-card",name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed"});console.info(`%c adjustable-bed-card %c ${We} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{x as AdjustableBedCard};
