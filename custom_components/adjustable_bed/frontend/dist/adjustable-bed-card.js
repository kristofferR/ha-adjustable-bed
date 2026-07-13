/* adjustable-bed-card 4.0.0b0 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var Ve=Object.defineProperty;var Ge=Object.getOwnPropertyDescriptor;var v=(o,s,e,t)=>{for(var i=t>1?void 0:t?Ge(s,e):s,r=o.length-1,n;r>=0;r--)(n=o[r])&&(i=(t?n(s,e,i):n(i))||i);return t&&i&&Ve(s,e,i),i};var V=globalThis,G=V.ShadowRoot&&(V.ShadyCSS===void 0||V.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,se=Symbol(),ye=new WeakMap,L=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==se)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(G&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=ye.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&ye.set(e,s))}return s}toString(){return this.cssText}},be=o=>new L(typeof o=="string"?o:o+"",void 0,se),U=(o,...s)=>{let e=o.length===1?o[0]:s.reduce((t,i,r)=>t+(n=>{if(n._$cssResult$===!0)return n.cssText;if(typeof n=="number")return n;throw Error("Value passed to 'css' function must be a 'css' function result: "+n+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+o[r+1],o[0]);return new L(e,o,se)},$e=(o,s)=>{if(G)o.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=V.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,o.appendChild(t)}},ie=G?o=>o:o=>o instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return be(e)})(o):o;var{is:Je,defineProperty:Ye,getOwnPropertyDescriptor:Xe,getOwnPropertyNames:Ze,getOwnPropertySymbols:Qe,getPrototypeOf:et}=Object,J=globalThis,xe=J.trustedTypes,tt=xe?xe.emptyScript:"",st=J.reactiveElementPolyfillSupport,D=(o,s)=>o,z={toAttribute(o,s){switch(s){case Boolean:o=o?tt:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,s){let e=o;switch(s){case Boolean:e=o!==null;break;case Number:e=o===null?null:Number(o);break;case Object:case Array:try{e=JSON.parse(o)}catch{e=null}}return e}},Y=(o,s)=>!Je(o,s),we={attribute:!0,type:String,converter:z,reflect:!1,useDefault:!1,hasChanged:Y};Symbol.metadata??=Symbol("metadata"),J.litPropertyMetadata??=new WeakMap;var b=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=we){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&Ye(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:r}=Xe(this.prototype,s)??{get(){return this[e]},set(n){this[e]=n}};return{get:i,set(n){let a=i?.call(this);r?.call(this,n),this.requestUpdate(s,a,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??we}static _$Ei(){if(this.hasOwnProperty(D("elementProperties")))return;let s=et(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(D("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(D("properties"))){let e=this.properties,t=[...Ze(e),...Qe(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(ie(i))}else s!==void 0&&e.push(ie(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return $e(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let r=(t.converter?.toAttribute!==void 0?t.converter:z).toAttribute(e,t.type);this._$Em=s,r==null?this.removeAttribute(i):this.setAttribute(i,r),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let r=t.getPropertyOptions(i),n=typeof r.converter=="function"?{fromAttribute:r.converter}:r.converter?.fromAttribute!==void 0?r.converter:z;this._$Em=i;let a=n.fromAttribute(e,r.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(s,e,t,i=!1,r){if(s!==void 0){let n=this.constructor;if(i===!1&&(r=this[s]),t??=n.getPropertyOptions(s),!((t.hasChanged??Y)(r,e)||t.useDefault&&t.reflect&&r===this._$Ej?.get(s)&&!this.hasAttribute(n._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:r},n){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,n??e??this[s]),r!==!0||n!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,r]of this._$Ep)this[i]=r;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,r]of t){let{wrapped:n}=r,a=this[i];n!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,r,a)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};b.elementStyles=[],b.shadowRootOptions={mode:"open"},b[D("elementProperties")]=new Map,b[D("finalized")]=new Map,st?.({ReactiveElement:b}),(J.reactiveElementVersions??=[]).push("2.1.2");var de=globalThis,Ee=o=>o,X=de.trustedTypes,Se=X?X.createPolicy("lit-html",{createHTML:o=>o}):void 0,Pe="$lit$",w=`lit$${Math.random().toFixed(9).slice(2)}$`,Te="?"+w,it=`<${Te}>`,A=document,I=()=>A.createComment(""),K=o=>o===null||typeof o!="object"&&typeof o!="function",he=Array.isArray,ot=o=>he(o)||typeof o?.[Symbol.iterator]=="function",oe=`[ 	
\f\r]`,F=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,ke=/-->/g,Ae=/>/g,S=RegExp(`>|${oe}(?:([^\\s"'>=/]+)(${oe}*=${oe}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Re=/'/g,Ce=/"/g,Oe=/^(?:script|style|textarea|title)$/i,pe=o=>(s,...e)=>({_$litType$:o,strings:s,values:e}),p=pe(1),He=pe(2),St=pe(3),R=Symbol.for("lit-noChange"),c=Symbol.for("lit-nothing"),Me=new WeakMap,k=A.createTreeWalker(A,129);function Be(o,s){if(!he(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return Se!==void 0?Se.createHTML(s):s}var rt=(o,s)=>{let e=o.length-1,t=[],i,r=s===2?"<svg>":s===3?"<math>":"",n=F;for(let a=0;a<e;a++){let l=o[a],m,_,f=-1,h=0;for(;h<l.length&&(n.lastIndex=h,_=n.exec(l),_!==null);)h=n.lastIndex,n===F?_[1]==="!--"?n=ke:_[1]!==void 0?n=Ae:_[2]!==void 0?(Oe.test(_[2])&&(i=RegExp("</"+_[2],"g")),n=S):_[3]!==void 0&&(n=S):n===S?_[0]===">"?(n=i??F,f=-1):_[1]===void 0?f=-2:(f=n.lastIndex-_[2].length,m=_[1],n=_[3]===void 0?S:_[3]==='"'?Ce:Re):n===Ce||n===Re?n=S:n===ke||n===Ae?n=F:(n=S,i=void 0);let d=n===S&&o[a+1].startsWith("/>")?" ":"";r+=n===F?l+it:f>=0?(t.push(m),l.slice(0,f)+Pe+l.slice(f)+w+d):l+w+(f===-2?a:d)}return[Be(o,r+(o[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},W=class o{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let r=0,n=0,a=s.length-1,l=this.parts,[m,_]=rt(s,e);if(this.el=o.createElement(m,t),k.currentNode=this.el.content,e===2||e===3){let f=this.el.content.firstChild;f.replaceWith(...f.childNodes)}for(;(i=k.nextNode())!==null&&l.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let f of i.getAttributeNames())if(f.endsWith(Pe)){let h=_[n++],d=i.getAttribute(f).split(w),P=/([.?@])?(.*)/.exec(h);l.push({type:1,index:r,name:P[2],strings:d,ctor:P[1]==="."?ne:P[1]==="?"?ae:P[1]==="@"?ce:O}),i.removeAttribute(f)}else f.startsWith(w)&&(l.push({type:6,index:r}),i.removeAttribute(f));if(Oe.test(i.tagName)){let f=i.textContent.split(w),h=f.length-1;if(h>0){i.textContent=X?X.emptyScript:"";for(let d=0;d<h;d++)i.append(f[d],I()),k.nextNode(),l.push({type:2,index:++r});i.append(f[h],I())}}}else if(i.nodeType===8)if(i.data===Te)l.push({type:2,index:r});else{let f=-1;for(;(f=i.data.indexOf(w,f+1))!==-1;)l.push({type:7,index:r}),f+=w.length-1}r++}}static createElement(s,e){let t=A.createElement("template");return t.innerHTML=s,t}};function T(o,s,e=o,t){if(s===R)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,r=K(s)?void 0:s._$litDirective$;return i?.constructor!==r&&(i?._$AO?.(!1),r===void 0?i=void 0:(i=new r(o),i._$AT(o,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=T(o,i._$AS(o,s.values),i,t)),s}var re=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??A).importNode(e,!0);k.currentNode=i;let r=k.nextNode(),n=0,a=0,l=t[0];for(;l!==void 0;){if(n===l.index){let m;l.type===2?m=new q(r,r.nextSibling,this,s):l.type===1?m=new l.ctor(r,l.name,l.strings,this,s):l.type===6&&(m=new le(r,this,s)),this._$AV.push(m),l=t[++a]}n!==l?.index&&(r=k.nextNode(),n++)}return k.currentNode=A,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},q=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=T(this,s,e),K(s)?s===c||s==null||s===""?(this._$AH!==c&&this._$AR(),this._$AH=c):s!==this._$AH&&s!==R&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):ot(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==c&&K(this._$AH)?this._$AA.nextSibling.data=s:this.T(A.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=W.createElement(Be(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let r=new re(i,this),n=r.u(this.options);r.p(e),this.T(n),this._$AH=r}}_$AC(s){let e=Me.get(s.strings);return e===void 0&&Me.set(s.strings,e=new W(s)),e}k(s){he(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let r of s)i===e.length?e.push(t=new o(this.O(I()),this.O(I()),this,this.options)):t=e[i],t._$AI(r),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=Ee(s).nextSibling;Ee(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},O=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,r){this.type=1,this._$AH=c,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=r,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=c}_$AI(s,e=this,t,i){let r=this.strings,n=!1;if(r===void 0)s=T(this,s,e,0),n=!K(s)||s!==this._$AH&&s!==R,n&&(this._$AH=s);else{let a=s,l,m;for(s=r[0],l=0;l<r.length-1;l++)m=T(this,a[t+l],e,l),m===R&&(m=this._$AH[l]),n||=!K(m)||m!==this._$AH[l],m===c?s=c:s!==c&&(s+=(m??"")+r[l+1]),this._$AH[l]=m}n&&!i&&this.j(s)}j(s){s===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},ne=class extends O{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===c?void 0:s}},ae=class extends O{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==c)}},ce=class extends O{constructor(s,e,t,i,r){super(s,e,t,i,r),this.type=5}_$AI(s,e=this){if((s=T(this,s,e,0)??c)===R)return;let t=this._$AH,i=s===c&&t!==c||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,r=s!==c&&(t===c||i);i&&this.element.removeEventListener(this.name,this,t),r&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},le=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){T(this,s)}};var nt=de.litHtmlPolyfillSupport;nt?.(W,q),(de.litHtmlVersions??=[]).push("3.3.3");var Ne=(o,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let r=e?.renderBefore??null;t._$litPart$=i=new q(s.insertBefore(I(),r),r,void 0,e??{})}return i._$AI(o),i};var ge=globalThis,y=class extends b{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=Ne(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return R}};y._$litElement$=!0,y.finalized=!0,ge.litElementHydrateSupport?.({LitElement:y});var at=ge.litElementPolyfillSupport;at?.({LitElement:y});(ge.litElementVersions??=[]).push("4.2.2");var Z=o=>(s,e)=>{e!==void 0?e.addInitializer(()=>{customElements.define(o,s)}):customElements.define(o,s)};var ct={attribute:!0,type:String,converter:z,reflect:!1,hasChanged:Y},lt=(o=ct,s,e)=>{let{kind:t,metadata:i}=e,r=globalThis.litPropertyMetadata.get(i);if(r===void 0&&globalThis.litPropertyMetadata.set(i,r=new Map),t==="setter"&&((o=Object.create(o)).wrapped=!0),r.set(e.name,o),t==="accessor"){let{name:n}=e;return{set(a){let l=s.get.call(this);s.set.call(this,a),this.requestUpdate(n,l,o,!0,a)},init(a){return a!==void 0&&this.C(n,void 0,o,a),a}}}if(t==="setter"){let{name:n}=e;return function(a){let l=this[n];s.call(this,a),this.requestUpdate(n,l,o,!0,a)}}throw Error("Unsupported decorator location: "+t)};function H(o){return(s,e)=>typeof e=="object"?lt(o,s,e):((t,i,r)=>{let n=i.hasOwnProperty(r);return i.constructor.createProperty(r,t),n?Object.getOwnPropertyDescriptor(i,r):void 0})(o,s,e)}function B(o){return H({...o,state:!0,attribute:!1})}var ue=o=>Math.max(0,Math.min(75,o));function je(o){let s=ue(o.upper.angle??0),e=ue(o.lower.angle??0),t=`rotate(${s} 150 70)`,i=`rotate(${-e} 150 70)`,r=n=>n.angle===void 0?"":`${n.label?`${n.label} `:""}${Math.round(ue(n.angle))}\xB0`;return He`
    <svg
      class="bed-graphic ${o.moving?"is-moving":""}"
      viewBox="0 0 300 110"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abMattress" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.95)" />
          <stop offset="100%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.6)" />
        </linearGradient>
        <linearGradient id="abFrame" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.45)" />
          <stop offset="100%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.2)" />
        </linearGradient>
      </defs>

      <!-- frame + legs -->
      <rect x="30" y="84" width="240" height="6" rx="3" fill="url(#abFrame)" />
      <rect x="34" y="88" width="5" height="14" rx="2" fill="url(#abFrame)" />
      <rect x="261" y="88" width="5" height="14" rx="2" fill="url(#abFrame)" />

      <!-- base mattress (static, behind the hinged panels) -->
      <rect x="42" y="64" width="216" height="20" rx="6"
        fill="rgba(var(--rgb-primary-color,33,150,243),0.28)" />

      <!-- foot panel (right of hinge) -->
      <g transform=${i} style="transition: transform 0.5s ease;">
        <rect x="150" y="58" width="108" height="18" rx="6" fill="url(#abMattress)" />
      </g>

      <!-- head/back panel (left of hinge) with pillow -->
      <g transform=${t} style="transition: transform 0.5s ease;">
        <rect x="42" y="58" width="108" height="18" rx="6" fill="url(#abMattress)" />
        <rect x="50" y="49" width="40" height="11" rx="5"
          fill="rgba(var(--rgb-primary-color,33,150,243),0.85)" />
      </g>

      <text x="86" y="22" text-anchor="middle" class="bed-graphic-label">${r(o.upper)}</text>
      <text x="214" y="22" text-anchor="middle" class="bed-graphic-label">${r(o.lower)}</text>
    </svg>
  `}var ee="adjustable_bed";function Ue(o){for(let s of["left","right","both"]){let e=`_${s}`;if(o.endsWith(e))return{key:o.slice(0,-e.length),side:s}}return{key:o}}var N=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],Le=["back","legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],me=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_incline","preset_both_up","preset_yoga"],dt=o=>o.split(".",1)[0],De=o=>o.translation_key??"";function ht(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[]},utility:[]}}function $(o,s,e){let t=ht();if(!s||!o?.entities)return t;let i=new Map,r=h=>{let d=i.get(h);return d||(d={key:h},i.set(h,d)),d},n=new Map,a=new Map,l=h=>{let d=a.get(h);return d||(d={slot:h},a.set(h,d)),d};for(let h of Object.values(o.entities)){if(h.device_id!==s||h.platform!==ee||h.hidden)continue;let d=h.entity_id,P=dt(d),te=De(h);if(!te)continue;let ve=Ue(te),qe=o.states[d]?.attributes.bed_side??o.states[d]?.attributes.side??ve.side;if(e&&qe!==e)continue;let g=e?ve.key:te,E;switch(P){case"cover":r(g).cover=d;break;case"sensor":g.endsWith("_angle")&&(r(g.slice(0,-6)).angle=d);break;case"number":g.endsWith("_position")?r(g.slice(0,-9)).position=d:g.startsWith("massage_")&&g.endsWith("_intensity")?t.massage.numbers.push(d):g==="light_level"?t.lights.level=d:g.startsWith("sleep_number_setting")&&t.firmness.push(d);break;case"button":me.includes(g)||g.startsWith("preset_")?(E=g.match(/^preset_memory_(\d+)$/))?l(Number(E[1])).goto=d:n.set(g,d):(E=g.match(/^program_memory_(\d+)$/))?l(Number(E[1])).save=d:g==="stop"||g==="stop_both"?t.stop=d:g==="connect"?t.connect=d:g==="disconnect"?t.disconnect=d:g==="toggle_light"?t.lights.toggle=d:g==="light_cycle"?t.lights.cycle=d:g==="sync_positions"||g==="child_lock_toggle"?t.utility.push(d):g.startsWith("massage_")?t.massage.buttons.push(d):(E=g.match(/^(.+)_(up|down)$/))&&(r(E[1])[E[2]]=d);break;case"switch":g==="under_bed_lights"?t.lights.switch=d:g==="synchro_mode"&&(t.synchro=d);break;case"light":t.lights.light=d;break;case"binary_sensor":g==="ble_connection"?t.connectivity=d:g.startsWith("bed_presence")&&t.presence.push(d);break;case"select":g==="light_timer"?t.lights.timer=d:g==="massage_timer"?t.massage.timer=d:/thermal|footwarming|foundation/.test(g)&&t.climate.selects.push(d);break;case"climate":t.climate.entities.push(d);break}}let m=[...i.keys()],_=[...Le.filter(h=>i.has(h)),...m.filter(h=>!Le.includes(h)).sort()];t.motors=_.map(h=>i.get(h)).filter(h=>h.cover||h.up||h.down||h.angle||h.position);let f=[...n.keys()];return t.presets=[...me.filter(h=>n.has(h)),...f.filter(h=>!me.includes(h)).sort()].map(h=>n.get(h)),t.memory=[...a.values()].filter(h=>h.goto||h.save).sort((h,d)=>h.slot-d.slot),t}function ze(o,s){return!s||!o?.entities?!1:Object.values(o.entities).some(e=>e.device_id===s&&e.platform===ee&&(o.states[e.entity_id]?.attributes.bed_side==="both"||Ue(De(e)).side==="both"))}function fe(o,s){if(!s||!o?.devices)return[];let e=t=>{let i=o.devices[t];return(i?.name_by_user??i?.name??t).toLowerCase()};return Object.values(o.devices).filter(t=>t.via_device_id===s).map(t=>t.id).sort((t,i)=>e(t)<e(i)?-1:e(t)>e(i)?1:0)}function Fe(o,s){if(!s||!o?.devices)return s;let e=o.devices[s]?.via_device_id;return e&&o.devices[e]&&fe(o,e).length?e:s}function j(o){let s=o.lights;return o.motors.length===0&&!o.synchro&&o.firmness.length===0&&o.presets.length===0&&o.memory.length===0&&!o.stop&&!o.connect&&!o.disconnect&&!o.connectivity&&!s.light&&!s.switch&&!s.level&&!s.toggle&&!s.cycle&&!s.timer&&o.massage.buttons.length===0&&o.massage.numbers.length===0&&!o.massage.timer&&o.climate.entities.length===0&&o.climate.selects.length===0&&o.utility.length===0}var Ie={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right"};var Ke={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre"};var C={en:Ie,nb:Ke};function ut(o){let s=(o?.locale?.language||o?.language||"en").toLowerCase(),e=s.split("-")[0];return C[s]?C[s]:C[e]?C[e]:e==="nn"||e==="no"?C.nb:C.en}function u(o,s,e){let i=ut(o)[s]??C.en[s]??s;if(e)for(let[r,n]of Object.entries(e))i=i.replace(`{${r}}`,n);return i}var We="4.0.0b0";var mt="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",ft="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z";function _t(o){return{graphic:o.motors.some(s=>s.angle),motors:o.motors.some(s=>s.cover||s.up||s.down)||!!o.stop||!!o.synchro,firmness:o.firmness.length>0,presets:o.presets.length>0,memory:o.memory.length>0,lighting:!!(o.lights.light||o.lights.switch||o.lights.level||o.lights.toggle||o.lights.cycle||o.lights.timer),massage:o.massage.buttons.length>0||o.massage.numbers.length>0||!!o.massage.timer,climate:o.climate.entities.length>0||o.climate.selects.length>0,connection:!!(o.connect||o.disconnect)}}var vt=(o,s)=>o.length===s.length&&o.every((e,t)=>e===s[t]),M=class extends y{constructor(){super(...arguments);this._computeLabel=e=>u(this.hass,`editor.${e.name}`)}setConfig(e){this._config=e}_bed(){let e=this._config?.device_id;if(!(!this.hass||!e))return $(this.hass,e)}_presentKeys(e){let t=_t(e);return N.filter(i=>t[i])}_orderedKeys(e){let t=this._presentKeys(e),r=(this._config?.section_order??[]).filter(a=>t.includes(a)),n=t.filter(a=>!r.includes(a));return[...r,...n]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=t&&this.hass?.states[t]?.attributes.friendly_name||`Memory ${e.slot}`,r=this._config?.device_id?this.hass?.devices[this._config.device_id]:void 0,n=r?.name_by_user||r?.name;return n&&i.startsWith(`${n} `)?i.slice(n.length+1):i}_emit(e){e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;i.device_id=t.device_id||void 0,t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let r=this._orderedKeys(e),n=r.indexOf(t),a=n+i;if(n<0||a<0||a>=r.length)return;[r[n],r[a]]=[r[a],r[n]];let l=this._cfg;vt(r,this._presentKeys(e))?delete l.section_order:l.section_order=r,this._emit(l)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let r=this._memorySlots(e),n=this._config?.memory_slots,a=n&&n.length?n.map(Number):[...r];i?a.includes(t)||a.push(t):a=a.filter(m=>m!==t),a.sort((m,_)=>m-_);let l=this._cfg;a.length===r.length?delete l.memory_slots:l.memory_slots=a,this._emit(l)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?p`
      <div class="group">
        <div class="group-title">${u(this.hass,"editor.sections")}</div>
        ${t.map((i,r)=>{let n=this._config?.[`show_${i}`]!==!1;return p`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${r===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${u(this.hass,"editor.move_up")}
                  aria-label=${u(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${mt}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${r===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${u(this.hass,"editor.move_down")}
                  aria-label=${u(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${ft}></path></svg>
                </button>
              </div>
              <span class="label">${u(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${n}
                @change=${a=>this._toggleSection(i,a.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:c}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return c;let i=e.memory.some(n=>n.save),r=e.memory.length>1;return!i&&!r?c:p`
      <div class="group">
        <div class="group-title">
          ${u(this.hass,"editor.memory_group")}
        </div>
        ${i?p`<div class="row">
                <span class="label">${u(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${n=>this._setMemorySave(n.target.checked)}
                ></ha-switch>
              </div>`:c}
        ${r?p`<div class="sub">
                <div class="sub-label">
                  ${u(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(n=>p`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(n.slot)}
                        @change=${a=>this._toggleSlot(e,n.slot,a.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(n)}</span>
                    </label>
                  `)}
              </div>`:c}
      </div>
    `}render(){if(!this.hass||!this._config)return c;let e=this._bed();return p`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${e?this._sectionsGroup(e):c}
      ${e?this._memoryGroup(e):c}
    `}};M.styles=U`
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
  `,v([H({attribute:!1})],M.prototype,"hass",2),v([B()],M.prototype,"_config",2),M=v([Z("adjustable-bed-card-editor")],M);var x=class extends y{constructor(){super(...arguments);this._activePairedPane="both";this._watched=[]}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===ee)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 8}shouldUpdate(e){if(e.has("_config")||e.has("_saveModeFor")||e.has("_activePairedPane")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices)return!0;for(let i of this._watched)if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return c;if(!this._config.device_id)return this._notice("card.no_device");let e=Fe(this.hass,this._config.device_id),t=fe(this.hass,e);if(e&&t.length)return this._renderPaired(e,t);if(this._config.device_id&&ze(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=$(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),j(i)?this._notice("card.no_entities"):p`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(e){let t=this._config,i={graphic:()=>t.show_graphic!==!1?this._graphic(e):c,motors:()=>t.show_motors!==!1?this._motors(e):c,firmness:()=>t.show_firmness!==!1?this._firmness(e):c,presets:()=>t.show_presets!==!1?this._presets(e):c,memory:()=>t.show_memory!==!1?this._memory(e):c,lighting:()=>t.show_lighting!==!1?this._lighting(e):c,massage:()=>t.show_massage!==!1?this._massage(e):c,utility:()=>t.show_utility!==!1?this._utility(e):c,climate:()=>t.show_climate!==!1?this._climate(e):c,connection:()=>t.show_connection!==!1?this._connection(e):c};return this._orderedSections().map(r=>i[r]?.()??c)}_renderPaired(e,t){let i=this.hass,r=$(i,e),n=t.map(a=>({key:a,label:this._deviceLabel(a),icon:"mdi:bed-single-outline",bed:$(i,a)}));return this._watched=[r,...n.map(a=>a.bed)].flatMap(a=>this._collectWatched(a)),j(r)&&n.every(a=>j(a.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:u(i,"card.both_sides"),icon:"mdi:link-variant",bed:r},...n])}_renderSingleAddressPaired(e){let t=this.hass,i={both:$(t,e,"both"),left:$(t,e,"left"),right:$(t,e,"right")};return this._watched=Object.values(i).flatMap(r=>this._collectWatched(r)),Object.values(i).every(r=>j(r))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:u(t,"card.both_sides"),icon:"mdi:link-variant",bed:i.both},{key:"left",label:u(t,"card.left_side"),icon:"mdi:bed-single-outline",bed:i.left},{key:"right",label:u(t,"card.right_side"),icon:"mdi:bed-single-outline",bed:i.right}])}_renderPairedCard(e,t){let i=t.filter(n=>!j(n.bed)),r=i.find(n=>n.key===this._activePairedPane)??i[0];return p`
      <ha-card class="paired-card">
        ${this._header(r.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(n=>p`
              <button
                class="pane-tab ${n.key===r.key?"active":""}"
                role="tab"
                aria-selected=${n.key===r.key?"true":"false"}
                @click=${()=>this._selectPairedPane(n.key)}
              >
                <ha-icon icon=${n.icon}></ha-icon>
                <span>${n.label}</span>
                ${this._connectionDot(n.bed)}
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${r.label}>
          ${this._renderSections(r.bed)}
        </div>
      </ha-card>
    `}_selectPairedPane(e){this._activePairedPane!==e&&(this._activePairedPane=e,this._saveModeFor=void 0)}_connectionDot(e){if(!e.connectivity)return c;let t=this._state(e.connectivity),i=t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected";return p`<span
      class="connection-dot ${i}"
      title=${u(this.hass,`status.${i}`)}
    ></span>`}_deviceLabel(e){let t=this.hass?.devices[e];return t?.name_by_user??t?.name??e}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...N];let t=new Set(N),i=e.filter(n=>t.has(n)),r=N.filter(n=>!i.includes(n));return[...i,...r]}_header(e,t){let i=e.connectivity?this._state(e.connectivity):void 0,r=e.connectivity?i?.state==="on"?"connected":i?.attributes?.state_detail==="idle"?"idle":"disconnected":void 0,n={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return p`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${r===void 0?c:p`
                <button
                  class="conn ${n[r].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${u(this.hass,n[r].key)}
                >
                  <ha-icon icon=${n[r].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e){let t=e.motors.filter(a=>a.angle);if(t.length===0)return c;let i=e.motors.find(a=>a.key==="back")??e.motors.find(a=>a.key==="head")??t[0],r=e.motors.find(a=>a.key==="legs")??e.motors.find(a=>a.key==="feet")??t[t.length-1],n=e.motors.some(a=>{let l=a.cover?this._state(a.cover)?.state:void 0;return l==="opening"||l==="closing"});return p`
      <div class="graphic">
        ${je({upper:{label:this._name(i.cover??i.angle),angle:this._angle(i)},lower:{label:this._name(r.cover??r.angle),angle:this._angle(r)},moving:n})}
      </div>
    `}_motors(e){let t=e.motors.filter(n=>n.cover||n.up||n.down),i=e.motors.filter(n=>!n.cover&&!n.up&&!n.down&&n.position);if(t.length===0&&i.length===0&&!e.synchro&&!e.stop)return c;let r=t.length>0||i.length>0||!!e.synchro;return p`
      ${r?this._heading("section.position"):c}
      ${e.synchro?this._toggleRow(e.synchro):c}
      ${t.length?p`<div class="rows">
              ${t.map(n=>this._motorRow(n,e.stop))}
            </div>`:c}
      ${i.length?p`<div class="rows">
              ${i.map(n=>this._moreInfoRow(n.position))}
            </div>`:c}
      ${e.stop?p`<button class="stop-all" @click=${()=>this._press(e.stop)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${u(this.hass,"action.stop_all")}</span>
            </button>`:c}
    `}_firmness(e){return e.firmness.length===0?c:p`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t){let i=this._readout(e),r=e.cover??e.up,n=e.cover??e.down,a=!!e.cover||!!t;return p`
      <div class="row">
        <div class="row-label">
          <span>${this._motorName(e)}</span>
          ${i?p`<span class="readout">${i}</span>`:c}
        </div>
        <div class="control-group">
          <button
            class="cg-btn"
            aria-label=${u(this.hass,"action.up")}
            @click=${()=>this._motorAction(e,"up")}
            ?disabled=${!r}
          >
            <ha-icon icon="mdi:chevron-up"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${u(this.hass,"action.stop")}
            @click=${()=>this._motorStop(e,t)}
            ?disabled=${!a}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${u(this.hass,"action.down")}
            @click=${()=>this._motorAction(e,"down")}
            ?disabled=${!n}
          >
            <ha-icon icon="mdi:chevron-down"></ha-icon>
          </button>
        </div>
      </div>
    `}_presets(e){return e.presets.length===0?c:p`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._tile(t,()=>this._press(t)))}
      </div>
    `}_utility(e){return e.utility.length===0?c:p`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${e.utility.map(t=>this._tile(t,()=>this._press(t)))}
      </div>
    `}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let l=new Set(i.map(Number));t=t.filter(m=>l.has(m.slot))}if(t.length===0)return c;let r=this._config?.memory_save!==!1&&t.some(l=>l.save),n=t.map(l=>l.save??l.goto??String(l.slot)).join("|"),a=this._saveModeFor===n;return p`
      <div class="section-heading heading-row">
        <span>${u(this.hass,"section.memory")}</span>
        ${r?p`<button
                class="set-btn ${a?"active":""}"
                @click=${()=>this._toggleSaveMode(n)}
              >
                <ha-icon
                  icon=${a?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${u(this.hass,a?"memory.cancel":"memory.set")}</span>
              </button>`:c}
      </div>
      ${a?p`<div class="hint">${u(this.hass,"memory.set_hint")}</div>`:c}
      <div class="tiles">${t.map(l=>this._memoryTile(l,a))}</div>
    `}_memoryTile(e,t){let i=e.goto??e.save;if(t){let n=!!e.save;return p`
        <button
          class="tile ${n?"save-mode":"is-disabled"}"
          ?disabled=${!n}
          @click=${()=>n&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(i)}</span>
        </button>
      `}let r=!!e.goto;return p`
      <button
        class="tile ${r?"":"is-disabled"}"
        ?disabled=${!r}
        @click=${()=>e.goto&&this._press(e.goto)}
      >
        ${this._icon(i)}
        <span class="tile-label">${this._name(i)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;return!i&&!t.level&&!t.timer&&!t.toggle&&!t.cycle?c:p`
      ${this._heading("section.lighting")}
      ${i?this._toggleRow(i):c}
      ${t.level?this._moreInfoRow(t.level):c}
      ${t.timer?this._moreInfoRow(t.timer):c}
      ${t.toggle||t.cycle?p`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):c}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):c}
            </div>`:c}
    `}_massage(e){let t=e.massage;return t.buttons.length===0&&t.numbers.length===0&&!t.timer?c:p`
      ${this._heading("section.massage")}
      ${t.buttons.length?p`<div class="tiles">
              ${t.buttons.map(i=>this._tile(i,()=>this._press(i)))}
            </div>`:c}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):c}
    `}_climate(e){let t=[...e.climate.entities,...e.climate.selects];return t.length===0?c:p`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?c:p`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):c}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):c}
      </div>
    `}_heading(e){return p`<div class="section-heading">${u(this.hass,e)}</div>`}_tile(e,t,i={}){return p`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${this._name(e)}</span>
      </button>
    `}_onRowKey(e,t){e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),t())}_toggleRow(e){let i=this._state(e)?.state==="on",r=this._name(e);return p`
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
      ></ha-state-icon>`:p`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return p`<ha-card><div class="notice">${u(this.hass,e)}</div></ha-card>`}_state(e){return this.hass?.states[e]}_title(e){return this._config?.name?this._config.name:this._deviceName(e)??u(this.hass,"card.default_name")}_deviceName(e=this._config?.device_id){let t=e?this.hass?.devices[e]:void 0;return t?.name_by_user||t?.name||void 0}_name(e){let t=this._state(e)?.attributes.friendly_name??this.hass?.entities[e]?.name??e,i=this.hass?.entities[e]?.device_id,r=this._deviceName(i);return r&&t.startsWith(r+" ")?t.slice(r.length+1):t}_motorName(e){let t=`motor.${e.key}`,i=u(this.hass,t);return i!==t?i:e.key.split("_").map(r=>r.charAt(0).toUpperCase()+r.slice(1)).join(" ")}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){if(e.angle){let t=this._angle(e);return t===void 0?void 0:`${Math.round(t)}\xB0`}if(e.position){let t=this._angle(e);return t===void 0?void 0:`${Math.round(t)}%`}if(e.cover){let t=this._state(e.cover)?.attributes.current_position;return typeof t=="number"?`${Math.round(t)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(r=>r&&t.add(r));e.presets.forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(r=>r&&t.add(r));return[e.stop,e.synchro,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),[...t]}_motorAction(e,t){if(e.cover)this._cover(e.cover,t==="up"?"open_cover":"close_cover");else{let i=t==="up"?e.up:e.down;i&&this._press(i)}}_motorStop(e,t){e.cover?this._cover(e.cover,"stop_cover"):t&&this._press(t)}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};x.styles=U`
    :host {
      --ab-gap: 10px;
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
      max-width: 320px;
      height: auto;
      overflow: visible;
    }
    .bed-graphic.is-moving {
      animation: ab-pulse 2s ease-in-out infinite;
    }
    .bed-graphic-label {
      fill: var(--secondary-text-color);
      font-size: 11px;
      font-family: var(--ha-font-family-body, var(--primary-font-family, sans-serif));
    }
    @keyframes ab-pulse {
      0%,
      100% {
        filter: drop-shadow(0 0 3px rgba(var(--rgb-primary-color, 33, 150, 243), 0.25));
      }
      50% {
        filter: drop-shadow(0 0 10px rgba(var(--rgb-primary-color, 33, 150, 243), 0.55));
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
    .notice {
      padding: 24px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }
  `,v([H({attribute:!1})],x.prototype,"hass",2),v([B()],x.prototype,"_config",2),v([B()],x.prototype,"_saveModeFor",2),v([B()],x.prototype,"_activePairedPane",2),x=v([Z("adjustable-bed-card")],x);var _e=window;_e.customCards=_e.customCards||[];_e.customCards.push({type:"adjustable-bed-card",name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed"});console.info(`%c adjustable-bed-card %c ${We} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{x as AdjustableBedCard};
