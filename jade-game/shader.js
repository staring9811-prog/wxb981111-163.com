/* 翡翠体渲染着色器。
 * 每个像素：先求视线与石头表面的交点，再沿视线向内部步进，累积“室内光 + 手电光”的散射。
 * 手电光从接触点进入：到任意内部点的光强 = 入射强度 × 沿途材质衰减(RGB 分通道) × 距离扩散 × 裂面遮挡。
 * 颜色只来自材质吸收，光源本身是白光。 */
window.JADE_VS = `#version 300 es
in vec2 aPos; void main(){ gl_Position=vec4(aPos,0.,1.); }`;
window.JADE_FS = `#version 300 es
precision highp float; precision highp sampler3D;
uniform sampler3D uGeom, uMat;
uniform vec2 uRes; uniform vec3 uCamPos; uniform mat3 uCamRot; uniform float uTan;
uniform vec3 uBox; uniform vec2 uClip; uniform float uPristine;
uniform vec3 uSkinCol; uniform float uSkinSig, uSkinGrain, uSkinRel, uWeather, uPhase;
uniform vec3 uBodyCol, uBandCol, uHueAbs, uFogCol; uniform float uFogT;
uniform int uNCr; uniform vec4 uCrA[6]; uniform vec4 uCrB[6]; uniform vec4 uCrC[6]; uniform vec3 uCrT[6];
uniform vec4 uTorch; uniform vec3 uTorchDir, uTorchSurf, uRakePos; uniform float uRakeFall, uRakeI, uSpread;
uniform float uAmbient; uniform vec4 uLens; uniform float uCutY; uniform int uK;
out vec4 outC;

float hash(vec3 p){ p=fract(p*0.3183099+vec3(.1,.2,.3)); p*=17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
float vnoise(vec3 x){ vec3 i=floor(x), f=fract(x); f=f*f*(3.0-2.0*f);
  return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z); }
float fbm(vec3 p){ return 0.5*vnoise(p)+0.3*vnoise(p*2.1+3.1)+0.2*vnoise(p*4.3+7.7); }
vec4 G(vec3 p){ return texture(uGeom,p/(2.0*uBox)+0.5); }
vec4 M(vec3 p){ return texture(uMat,p/(2.0*uBox)+0.5); }
float sdfOf(vec4 g){ return mix(g.g,g.r,uPristine); }

// 材质光学：种水越高衰减越小、散射越弱；色素吸收红蓝；棉增散射；脏全吸收
vec3 sigT(vec4 m){ float b=mix(0.20,0.006,pow(smoothstep(0.03,0.97,m.g),0.6));
  vec3 s=b*vec3(0.90,1.0,1.22); s+=m.r*uHueAbs*0.30; s+=(1.0-uBodyCol)*0.05; s+=m.b*0.10; s+=m.a*vec3(0.6,0.55,0.5); return s; }
float scat(vec4 m){ return mix(0.50,0.03,pow(m.g,0.7))+m.b*0.3; }
vec3 albedo(vec4 m){ vec3 a=mix(uBodyCol,uBandCol,clamp(m.r*1.2,0.,1.)); a=mix(a,vec3(0.97),m.b*0.6); return a*(1.0-0.8*m.a); }

float crG(int i, vec3 p, out float ins){
  vec3 d=p-uCrA[i].xyz; vec3 n=uCrB[i].xyz; float h=dot(d,n); vec3 q=d-n*h; float r=length(q);
  vec3 t1=uCrT[i]; vec3 t2=cross(n,t1); float a=dot(q,t1), b=dot(q,t2);
  h+=uCrC[i].x*(sin(a*uCrC[i].y+uCrC[i].z)+sin(b*uCrC[i].y*1.37+uCrC[i].z*2.1))*0.5;
  float R=uCrA[i].w*(1.0+0.18*sin(atan(b,a)*3.0+uCrC[i].z)); ins=1.0-smoothstep(R*0.85,R,r); return h; }
float segT(vec3 A, vec3 B){ float T=1.0;
  for(int i=0;i<6;i++){ if(i>=uNCr) break; float ia,ib; float ga=crG(i,A,ia), gb=crG(i,B,ib);
    if(ga*gb<0.0){ float t=ga/(ga-gb); T*=1.0-mix(ia,ib,t)*uCrB[i].w*0.80; } }
  return T; }
vec3 fluence(vec3 s){
  vec3 d=s-uTorch.xyz; float r=length(d); vec3 dn=d/max(r,1e-3); vec3 tau=vec3(0.0);
  for(int j=0;j<4;j++){ tau+=sigT(M(uTorch.xyz+d*((float(j)+0.5)/4.0))); }
  tau*=r/4.0;
  float geo=1.0/(1.0+r*r/uSpread);
  float beam=mix(0.30,1.0,smoothstep(-0.3,0.8,dot(dn,uTorchDir)));
  return uTorch.w*exp(-tau)*geo*beam*segT(uTorch.xyz,s); }

vec3 calcN(vec3 p){ const float e=1.0; vec2 k=vec2(1.,-1.);
  return normalize(k.xyy*sdfOf(G(p+k.xyy*e))+k.yyx*sdfOf(G(p+k.yyx*e))+k.yxy*sdfOf(G(p+k.yxy*e))+k.xxx*sdfOf(G(p+k.xxx*e))); }
bool trace(vec3 ro, vec3 rd, out vec3 p, out vec3 n){
  vec3 bmin=vec3(-uBox.x,max(-uBox.y,uClip.x),-uBox.z), bmax=vec3(uBox.x,min(uBox.y,uClip.y),uBox.z);
  vec3 inv=1.0/(rd+vec3(1e-6)); vec3 t0=(bmin-ro)*inv, t1=(bmax-ro)*inv; vec3 a=min(t0,t1), b=max(t0,t1);
  float tn=max(max(a.x,a.y),a.z), tf=min(min(b.x,b.y),b.z);
  if(tn>tf||tf<0.0) return false;
  float t=max(tn,0.0)+0.01; p=ro+rd*t;
  if(sdfOf(G(p))<0.0){ n=vec3(0.,-sign(rd.y),0.); return true; }
  float d=1.0;
  for(int i=0;i<128;i++){ p=ro+rd*t; d=sdfOf(G(p)); if(d<0.05){ n=calcN(p); return true; } t+=max(d*0.8,0.12); if(t>tf) return false; }
  if(d<0.8){ n=calcN(p); return true; }
  return false; }

vec3 shade(vec3 p, vec3 n, vec3 rd, float detail){
  vec4 g=G(p); float depth0=-g.r; float skinT=g.b;
  float flesh=smoothstep(skinT-0.3,skinT+0.3,depth0);
  vec3 keyL=normalize(uCamRot*vec3(-0.5,0.65,0.6));
  vec3 surf=vec3(0.0);
  if(flesh<0.999){
    float gf=mix(2.4,0.8,uSkinGrain);
    float gr=vnoise(p*gf+uPhase), gr2=vnoise(p*gf*2.7+uPhase+9.0);
    float blot=fbm(p*0.045+uPhase);
    vec3 col=uSkinCol*(0.70+0.6*blot);
    col=mix(col,col*vec3(1.25,0.82,0.6),uWeather*smoothstep(0.5,0.75,fbm(p*0.09+uPhase+20.0)));
    col*=0.78+0.44*mix(gr,gr2,0.4);
    if(detail>0.5){ col*=0.80+0.40*vnoise(p*gf*6.0+uPhase+3.0); col*=0.90+0.20*vnoise(p*gf*14.0+uPhase); }
    vec4 b1=M(p-n*(skinT+2.0)), b2=M(p-n*(skinT+5.0));
    // 松花、蟒带、癣：部分来自皮下真相，部分是与内部无关的假象，比例由场口可靠度决定
    float cT=max(b1.r,b2.r*0.7);
    float fake=smoothstep(0.62,0.80,vnoise(p*0.045+uPhase+31.7));
    float hint=mix(fake*0.8,cT,uSkinRel);
    float speck=smoothstep(0.42,0.72,vnoise(p*1.3+7.0+uPhase));
    col=mix(col,mix(vec3(0.22,0.40,0.20),uBandCol,0.5),clamp(hint*speck*0.85,0.,1.));
    float mang=smoothstep(0.5,0.8,mix(vnoise(p*0.03+uPhase*2.0),b1.g,uSkinRel))*smoothstep(0.45,0.6,vnoise(p*vec3(0.03,0.2,0.03)+uPhase));
    col=mix(col,col*1.22+0.04,mang*0.5);
    col=mix(col,vec3(0.05,0.06,0.05),smoothstep(0.2,0.6,max(b1.a,b2.a))*0.8*uSkinRel);
    for(int i=0;i<6;i++){ if(i>=uNCr) break; if(uCrC[i].w>0.5){ float ins; float h=crG(i,p,ins);
      col*=1.0-0.75*(1.0-smoothstep(0.12,0.45,abs(h)))*ins*uCrB[i].w; } }
    vec3 ns=normalize(n+(vec3(vnoise(p*gf+uPhase+1.7),vnoise(p*gf+uPhase+5.3),gr)-0.5)*(0.5*uSkinGrain+0.2+detail*0.25));
    surf=col*(0.22+0.62*max(dot(ns,keyL),0.0))*uAmbient;
    if(uTorch.w>0.0){ vec3 dl=uRakePos-p; float dd=length(dl); surf+=col*max(dot(ns,dl/dd),0.0)/(1.0+dd*dd/uRakeFall)*uRakeI; }
  }
  vec3 dir=normalize(rd-n*mix(0.6,0.25,flesh));
  vec3 x=p-n*mix(skinT+0.4,0.05,flesh);
  vec3 tint=mix(vec3(1.0),uSkinCol/max(max(uSkinCol.r,uSkinCol.g),uSkinCol.b),0.7);
  vec3 T0=mix(exp(-uSkinSig*skinT)*tint,vec3(1.0),flesh);
  vec3 T=T0, acc=vec3(0.0); float dt=0.45, trav=0.0; float gp[6];
  for(int i=0;i<6;i++){ float ins; gp[i]=i<uNCr?crG(i,x,ins):1.0; }
  float ambL=uAmbient*(0.5+0.5*max(dot(n,keyL),0.0));
  for(int k=0;k<16;k++){ if(k>=uK) break;
    vec3 s=x+dir*dt*0.5; vec4 gs=G(s); float ds=max(sdfOf(gs),max(s.y-uClip.y,uClip.x-s.y));
    if(ds>0.4) break;
    vec4 m=M(s); vec3 sg=sigT(m); float sc=scat(m); vec3 al=albedo(m);
    float fogw=uFogT>0.0?1.0-smoothstep(gs.b+uFogT*0.6,gs.b+uFogT,-gs.r):0.0; al=mix(al,uFogCol,fogw*0.75); sg+=fogw*0.10;
    if(detail>0.5){ float cg=mix(vnoise(s*2.2+3.0),vnoise(s*6.5+1.0),0.5); al*=1.0+(cg-0.5)*0.7*(1.0-m.g); sc*=1.0+(cg-0.5)*1.2*(1.0-m.g); }
    vec3 Lin=T0*mix(T0*0.4,vec3(0.42),flesh)*ambL*exp(-sg*trav*0.5);
    if(uTorch.w>0.0) Lin+=fluence(s);
    vec3 xe=x+dir*dt;
    for(int i=0;i<6;i++){ if(i>=uNCr) break; float ins; float h=crG(i,xe,ins);
      if(h*gp[i]<0.0&&ins>0.3){ float op=uCrB[i].w; vec3 gl=T0*ambL*0.5; if(uTorch.w>0.0) gl+=fluence(xe); acc+=T*gl*op*0.45; T*=1.0-0.5*op; }
      gp[i]=h; }
    acc+=T*al*sc*dt*Lin; T*=exp(-sg*dt); x=xe; trav+=dt; dt*=1.2;
  }
  float line=0.0;
  for(int i=0;i<6;i++){ if(i>=uNCr) break; float ins; float h=crG(i,p,ins); line=max(line,(1.0-smoothstep(0.1,0.35,abs(h)))*ins*uCrB[i].w); }
  acc*=1.0-0.6*line*flesh;
  float spec=pow(max(dot(reflect(-keyL,n),-rd),0.0),48.0)*0.5*uAmbient*flesh;
  vec3 col=surf*(1.0-flesh)+acc+spec;
  if(uTorch.w>0.0){ float r=length(p-uTorchSurf); col+=vec3(1.0,0.97,0.9)*min(uTorch.w,6.0)*0.05*exp(-r*r/9.0); col+=vec3(0.5)*(smoothstep(4.0,4.4,r)-smoothstep(4.6,5.0,r))*0.35; }
  if(abs(p.y-uCutY)<0.4) col=mix(col,vec3(1.0,0.55,0.15),0.85);
  return col; }

void main(){
  vec2 px=gl_FragCoord.xy; float detail=0.0; float rim=0.0;
  if(uLens.z>0.0){ float d=length(px-uLens.xy); if(d<uLens.z){ px=uLens.xy+(px-uLens.xy)/uLens.w; detail=1.0; } rim=smoothstep(uLens.z-3.0,uLens.z-1.0,d)-smoothstep(uLens.z+1.0,uLens.z+3.0,d); }
  vec2 uv=(px-0.5*uRes)/(0.5*uRes.y);
  vec3 rd=normalize(uCamRot*vec3(uv*uTan,-1.0));
  vec2 c=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  vec3 col=mix(vec3(0.085,0.075,0.065),vec3(0.02,0.018,0.016),clamp(length(c)*1.5,0.,1.))*(0.35+0.65*uAmbient);
  vec3 p,n;
  if(trace(uCamPos,rd,p,n)) col=shade(p,n,rd,detail);
  col=1.0-exp(-col*1.5);
  col=pow(col,vec3(1.0/2.2));
  col=mix(col,vec3(0.75,0.7,0.6),rim*0.9);
  outC=vec4(col,1.0);
}`;
