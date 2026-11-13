/* 翡翠体渲染着色器。
 * 每个像素：先求视线与石头表面的交点，再沿视线向内部步进，累积“室内光 + 手电光”的散射。
 * 手电光从接触点进入：到任意内部点的光强 = 入射强度 × 沿途材质衰减(RGB 分通道) × 距离扩散 × 裂面遮挡。
 * 颜色只来自材质吸收，光源本身是白光。表面另有：皮壳凹凸、主光软阴影、环境遮蔽、玉肉菲涅耳反光。 */
window.JADE_VS = `#version 300 es
in vec2 aPos; void main(){ gl_Position=vec4(aPos,0.,1.); }`;
window.JADE_FS = `#version 300 es
precision highp float; precision highp sampler3D;
uniform sampler3D uGeom, uMat;
uniform vec2 uRes; uniform vec3 uCamPos; uniform mat3 uCamRot; uniform float uTan;
uniform vec3 uBox; uniform float uPristine; uniform int uNPl; uniform vec4 uPl[16]; uniform vec4 uCut; uniform float uCutOn;
uniform vec3 uSkinCol; uniform float uSkinSig, uSkinGrain, uSkinRel, uWeather, uPhase;
uniform vec3 uBodyCol, uBandCol, uHueAbs, uFogCol; uniform float uFogT;
uniform int uNCr; uniform vec4 uCrA[6]; uniform vec4 uCrB[6]; uniform vec4 uCrC[6]; uniform vec3 uCrT[6];
uniform vec4 uTorch; uniform vec3 uTorchDir, uTorchSurf, uRakePos; uniform float uRakeFall, uRakeI, uSpread;
uniform vec3 uGlare; // 手电接触点的屏幕位置 xy（像素）与可见强度
uniform float uAmbient; uniform vec4 uLens; uniform int uK; uniform float uHi;
uniform vec3 uBgA, uBgB, uKeyCol; uniform int uScene;
out vec4 outC;

float hash(vec3 p){ p=fract(p*0.3183099+vec3(.1,.2,.3)); p*=17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
float vnoise(vec3 x){ vec3 i=floor(x), f=fract(x); f=f*f*(3.0-2.0*f);
  return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z); }
float fbm(vec3 p){ return 0.5*vnoise(p)+0.3*vnoise(p*2.1+3.1)+0.2*vnoise(p*4.3+7.7); }
float ign(vec2 p){ return fract(52.9829189*fract(dot(p,vec2(0.06711056,0.00583715)))); }
vec4 G(vec3 p){ return texture(uGeom,p/(2.0*uBox)+0.5); }
vec4 M(vec3 p){ return texture(uMat,p/(2.0*uBox)+0.5); }
// 用小尺度噪声扰动取样位置，让色带边缘呈絮状、丝状，而不是体素的糊边
vec4 Mw(vec3 p){ vec3 w=vec3(vnoise(p*0.55+11.0),vnoise(p*0.55+37.0),vnoise(p*0.55+71.0))-0.5; return M(p+w*2.2); }
float sdfOf(vec4 g){ return mix(g.g,g.r,uPristine); }
float planeD(vec3 p){ float m=-1e9; for(int i=0;i<16;i++){ if(i>=uNPl) break; m=max(m,dot(p,uPl[i].xyz)-uPl[i].w); } return m; }
float mapD(vec3 p){ return max(sdfOf(G(p)),planeD(p)); }

vec3 sigT(vec4 m){ float b=max(0.005,0.42*exp(-4.6*m.g)); // 豆 0.27 → 冰 0.02 → 玻璃 0.005，每毫米
  vec3 s=b*vec3(0.90,1.0,1.22); s+=m.r*uHueAbs*0.30; s+=(1.0-uBodyCol)*0.05; s+=m.b*0.10; s+=m.a*vec3(0.6,0.55,0.5); return s; }
float scat(vec4 m){ return max(0.02,0.62*exp(-3.6*m.g))+m.b*0.3; }
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
bool trace(vec3 ro, vec3 rd, out vec3 p, out vec3 n, out float flat_){
  vec3 inv=1.0/(rd+vec3(1e-6)); vec3 t0=(-uBox-ro)*inv, t1=(uBox-ro)*inv; vec3 a=min(t0,t1), b=max(t0,t1);
  float tn=max(max(a.x,a.y),a.z), tf=min(min(b.x,b.y),b.z); flat_=0.0;
  if(tn>tf||tf<0.0) return false;
  float t=max(tn,0.0)+0.01; float d=1.0, sd=1.0, pd=-1e9, tp=t;
  for(int i=0;i<150;i++){ p=ro+rd*t; sd=sdfOf(G(p)); pd=planeD(p); d=max(sd,pd);
    if(d<0.02) break; tp=t; t+=max(d*0.8,0.10); if(t>tf) return false; }
  if(d>0.8) return false;
  // 二分细化交点，让轮廓和窗口边缘更干净
  float ta=tp, tb=t; for(int i=0;i<5;i++){ float tm=0.5*(ta+tb); if(mapD(ro+rd*tm)<0.0) tb=tm; else ta=tm; }
  p=ro+rd*tb; sd=sdfOf(G(p)); pd=planeD(p);
  if(pd>sd-0.06){ float m=-1e9; for(int i=0;i<16;i++){ if(i>=uNPl) break; float v=dot(p,uPl[i].xyz)-uPl[i].w; if(v>m){ m=v; n=uPl[i].xyz; } } flat_=1.0; }
  else n=calcN(p);
  return true; }
float softShadow(vec3 p, vec3 l){ float res=1.0, t=2.5; for(int i=0;i<10;i++){ float d=mapD(p+l*t); res=min(res,7.0*d/t); t+=clamp(d,1.5,7.0); if(res<0.02||t>70.0) break; } return clamp(res,0.0,1.0); }
float calcAO(vec3 p, vec3 n){ float o=0.0, w=1.0; for(int i=1;i<=4;i++){ float h=float(i)*2.4; o+=w*(h-mapD(p+n*h)); w*=0.6; } return clamp(1.0-0.16*o,0.0,1.0); }
// 皮壳高度场：大起伏 + 砂粒
float skinH(vec3 p, float gf){ return 0.9*fbm(p*0.22+uPhase)+uSkinGrain*(0.55*vnoise(p*gf+uPhase)+0.30*vnoise(p*gf*2.3+uPhase+5.0)+0.15*vnoise(p*gf*5.1+uPhase+9.0)); }
vec3 envLight(vec3 r, vec3 keyL){ // 假想的摄影棚：一盏主柔光箱 + 顶部漫射 + 暗的地面
  float box=smoothstep(0.80,0.97,dot(r,keyL)); float top=smoothstep(-0.2,0.9,r.y);
  return vec3(1.0,0.97,0.92)*box*2.2+vec3(0.20,0.21,0.23)*top+vec3(0.03,0.028,0.025); }

vec3 shade(vec3 p, vec3 n, vec3 rd, float detail, float flat_){
  vec4 g=G(p); float depth0=-g.r; float skinT=g.b;
  float flesh=smoothstep(skinT-0.3,skinT+0.3,depth0);
  vec3 keyL=normalize(uCamRot*vec3(-0.55,0.62,0.56));
  vec3 fillL=normalize(uCamRot*vec3(0.75,0.15,0.45));
  vec3 rimL=normalize(uCamRot*vec3(0.25,0.55,-0.80));
  float ao=1.0, sh=1.0;
  if(uHi>0.5){ ao=calcAO(p,n); sh=softShadow(p+n*0.6,keyL); }
  vec3 surf=vec3(0.0);
  if(flesh<0.999){
    float gf=mix(2.4,0.8,uSkinGrain)*(1.0+detail*0.6);
    float gr=vnoise(p*gf+uPhase), gr2=vnoise(p*gf*2.7+uPhase+9.0), gr3=vnoise(p*gf*6.0+uPhase+3.0);
    float blot=fbm(p*0.045+uPhase), mid=fbm(p*0.16+uPhase+40.0);
    vec3 col=uSkinCol*(0.62+0.5*blot+0.28*mid);
    col=mix(col,col*vec3(1.28,0.80,0.56),uWeather*smoothstep(0.5,0.75,fbm(p*0.09+uPhase+20.0)));
    col=mix(col,col*vec3(0.80,0.84,0.92),0.5*smoothstep(0.55,0.8,fbm(p*0.07+uPhase+60.0)));
    col*=0.74+0.30*gr+0.20*gr2+0.12*gr3;
    col*=1.0-0.45*smoothstep(0.24,0.10,gr2)*uSkinGrain;            // 砂眼小坑
    col+=vec3(0.10,0.095,0.085)*smoothstep(0.86,0.95,gr3)*uSkinGrain; // 浅色砂粒
    vec4 b1=M(p-n*(skinT+2.0)), b2=M(p-n*(skinT+5.0));
    // 松花、蟒带、癣：部分来自皮下真相，部分是与内部无关的假象，比例由场口可靠度决定
    float cT=max(b1.r,b2.r*0.7);
    float fake=smoothstep(0.62,0.80,vnoise(p*0.045+uPhase+31.7));
    float hint=mix(fake*0.8,cT,uSkinRel);
    float speck=smoothstep(0.42,0.72,vnoise(p*1.3+7.0+uPhase))*(0.6+0.4*vnoise(p*3.1+uPhase));
    col=mix(col,mix(vec3(0.20,0.38,0.19),uBandCol,0.5),clamp(hint*speck*0.9,0.,1.));
    float mang=smoothstep(0.5,0.8,mix(vnoise(p*0.03+uPhase*2.0),b1.g,uSkinRel))*smoothstep(0.45,0.6,vnoise(p*vec3(0.03,0.2,0.03)+uPhase));
    col=mix(col,col*1.22+0.04,mang*0.5);
    col=mix(col,vec3(0.05,0.06,0.05),smoothstep(0.2,0.6,max(b1.a,b2.a))*0.8*uSkinRel);
    float crk=0.0; // 到皮的裂：明显的是黑线带锈边，隐蔽的只是一条细发丝
    for(int i=0;i<6;i++){ if(i>=uNCr) break; float ins; float h=crG(i,p,ins); float vis=mix(0.38,1.0,uCrC[i].w)*uCrB[i].w*ins;
      col=mix(col,col*vec3(1.15,0.72,0.5),(1.0-smoothstep(0.5,2.2,abs(h)))*vis*0.45);
      float l=(1.0-smoothstep(0.14,mix(0.45,0.80,uCrC[i].w),abs(h)))*vis; col*=1.0-0.85*l; crk=max(crk,l); }
    // 凹凸：对高度场做有限差分
    float e=0.35; float h0=skinH(p,gf);
    vec3 gh=vec3(skinH(p+vec3(e,0,0),gf),skinH(p+vec3(0,e,0),gf),skinH(p+vec3(0,0,e),gf))-h0;
    gh-=n*dot(gh,n);
    vec3 ns=normalize(n-gh*(1.6+detail*0.8)*(1.0-mang*0.6));
    float cav=smoothstep(0.25,0.75,h0/(0.9+uSkinGrain));              // 凹处更暗
    float dif=max(dot(ns,keyL),0.0)*sh;
    vec3 lit=uKeyCol*dif*0.95+vec3(0.55,0.62,0.75)*max(dot(ns,fillL),0.0)*0.22+vec3(0.9,0.9,1.0)*pow(max(dot(ns,rimL),0.0),2.0)*0.18+vec3(0.20,0.19,0.18)*ao*(0.6+0.4*ns.y);
    vec3 hv=normalize(keyL-rd); float gloss=mix(0.22,0.05,uSkinGrain);
    float sp=pow(max(dot(ns,hv),0.0),mix(30.0,10.0,uSkinGrain))*gloss*sh;
    surf=(col*(0.72+0.38*cav)*lit+vec3(sp))*uAmbient;
    if(uTorch.w>0.0){ vec3 dl=uRakePos-p; float dd=length(dl); surf+=col*max(dot(ns,dl/dd),0.0)/(1.0+dd*dd/uRakeFall)*uRakeI; }
  }
  // 玉肉表面：切面抛光感强，磨出的窗口偏哑光
  vec3 nf=n;
  if(flesh>0.001&&flat_<0.5){ vec3 w=vec3(vnoise(p*1.7+3.0),vnoise(p*1.7+13.0),vnoise(p*1.7+23.0))-0.5; nf=normalize(n+w*0.10); }
  vec3 dir=normalize(rd-n*mix(0.6,0.25,flesh));
  vec3 x=p-n*mix(skinT+0.4,0.05,flesh);
  vec3 tint=mix(vec3(1.0),uSkinCol/max(max(uSkinCol.r,uSkinCol.g),uSkinCol.b),0.7);
  vec3 T0=mix(exp(-uSkinSig*skinT)*tint,vec3(1.0),flesh);
  vec3 T=T0, acc=vec3(0.0); float dt=0.40, trav=0.0; float gp[6];
  x+=dir*dt*(ign(gl_FragCoord.xy)-0.5)*0.9*flesh;   // 抖动起点，消除分层条纹
  for(int i=0;i<6;i++){ float ins; gp[i]=i<uNCr?crG(i,x,ins):1.0; }
  float ambL=uAmbient*(0.42+0.58*max(dot(nf,keyL),0.0)*mix(1.0,sh,0.6))*mix(1.0,ao,0.5);
  vec3 ambC=mix(vec3(1.0),uKeyCol,0.85); // 场景灯光的颜色会改变你看到的色：黄灯下绿显得更浓
  for(int k=0;k<18;k++){ if(k>=uK) break;
    vec3 s=x+dir*dt*0.5; vec4 gs=G(s); float ds=max(sdfOf(gs),planeD(s));
    if(ds>0.4) break;
    vec4 m=Mw(s); vec3 sg=sigT(m); float sc=scat(m); vec3 al=albedo(m);
    float fogw=uFogT>0.0?1.0-smoothstep(gs.b+uFogT*0.6,gs.b+uFogT,-gs.r):0.0; al=mix(al,uFogCol,fogw*0.75); sg+=fogw*0.10;
    // 晶粒：种越嫩颗粒越明显；放大镜下更清楚
    float cg=mix(vnoise(s*1.6+3.0),vnoise(s*4.5+1.0),0.45)-0.5; float gk=(1.0-m.g)*(0.30+detail*0.55);
    al*=1.0+cg*gk; sc*=1.0+cg*gk*1.6;
    vec3 Lin=ambC*T0*mix(T0*0.4,vec3(mix(0.62,0.26,m.g)),flesh)*ambL*exp(-sg*trav*0.5);
    if(uTorch.w>0.0) Lin+=fluence(s);
    vec3 xe=x+dir*dt;
    for(int i=0;i<6;i++){ if(i>=uNCr) break; float ins; float h=crG(i,xe,ins);
      if(h*gp[i]<0.0&&ins>0.3){ float op=uCrB[i].w; vec3 gl=T0*ambL*0.5; if(uTorch.w>0.0) gl+=fluence(xe); acc+=T*gl*op*0.45; T*=1.0-0.5*op; }
      gp[i]=h; }
    acc+=T*al*sc*dt*Lin; T*=exp(-sg*dt); x=xe; trav+=dt; dt*=1.19;
  }
  float line=0.0, halo=0.0; // 露肉面上的裂：一条暗线，两侧发白起雾，大裂带锈色
  for(int i=0;i<6;i++){ if(i>=uNCr) break; float ins; float h=crG(i,p,ins); float o=ins*uCrB[i].w;
    line=max(line,(1.0-smoothstep(0.10,0.50,abs(h)))*o); halo=max(halo,(1.0-smoothstep(0.4,2.4,abs(h)))*o); }
  acc=mix(acc,acc*vec3(1.0,0.86,0.70)+vec3(0.10,0.095,0.085)*uAmbient,halo*0.55*flesh);
  acc*=1.0-0.80*line*flesh;
  if(flat_>0.5) acc*=1.0+0.035*sin(dot(p,uCamRot[0])*5.0+vnoise(p*0.3)*4.0)*flesh; // 锯痕
  // 菲涅耳反光：种水越好表面越“起光”
  float wS=M(p-n*0.5).g; float ndv=max(dot(nf,-rd),0.0);
  float F=(0.035+0.965*pow(1.0-ndv,5.0))*mix(0.45,1.0,wS)*mix(0.55,1.0,flat_);
  vec3 refl=envLight(reflect(rd,nf),keyL)*mix(1.0,sh,0.7);
  vec3 hv2=normalize(keyL-rd); float spec=pow(max(dot(nf,hv2),0.0),mix(40.0,220.0,flat_*0.6+wS*0.4))*mix(0.5,1.6,wS)*sh;
  vec3 col=surf*(1.0-flesh)+acc+(refl*F+vec3(spec)*0.5)*uAmbient*flesh;
  if(uTorch.w>0.0){ float r=length(p-uTorchSurf); col+=vec3(1.0,0.97,0.9)*min(uTorch.w,6.0)*0.06*exp(-r*r/9.0); col+=vec3(0.5)*(smoothstep(4.0,4.4,r)-smoothstep(4.6,5.0,r))*0.30; }
  if(uCutOn>0.5&&abs(dot(p,uCut.xyz)-uCut.w)<0.45) col=mix(col,vec3(1.0,0.55,0.15),0.85);
  return col; }

vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }
void main(){
  vec2 px=gl_FragCoord.xy; float detail=0.0; float rim=0.0;
  if(uLens.z>0.0){ float d=length(px-uLens.xy); if(d<uLens.z){ px=uLens.xy+(px-uLens.xy)/uLens.w; detail=1.0; } rim=smoothstep(uLens.z-3.0,uLens.z-1.0,d)-smoothstep(uLens.z+1.0,uLens.z+3.0,d); }
  vec2 uv=(px-0.5*uRes)/(0.5*uRes.y);
  vec3 rd=normalize(uCamRot*vec3(uv*uTan,-1.0));
  vec2 c=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  // 背景：暗色台面，中间一团柔光，四周压暗
  float spot=exp(-dot(c*vec2(1.0,1.25)-vec2(0.0,-0.05),c*vec2(1.0,1.25)-vec2(0.0,-0.05))*2.6);
  vec3 col=mix(uBgB,uBgA,spot);
  if(uScene==0){ // 夜市：远处虚化的灯泡
    for(int i=0;i<7;i++){ vec2 q=vec2(hash(vec3(float(i),1.0,2.0))*1.9-0.95,0.12+hash(vec3(float(i),5.0,3.0))*0.36); float r=0.035+0.05*hash(vec3(float(i),9.0,4.0));
      col+=mix(vec3(1.0,0.62,0.25),vec3(1.0,0.85,0.55),hash(vec3(float(i),2.0,7.0)))*(1.0-smoothstep(r*0.35,r,length(c-q)))*0.10; }
    col+=vec3(0.16,0.085,0.03)*exp(-dot(c-vec2(-0.45,0.55),c-vec2(-0.45,0.55))*3.0);
  } else if(uScene==2){ // 公盘：顶上一束冷光
    col+=vec3(0.10,0.13,0.18)*exp(-c.x*c.x*7.0)*smoothstep(-0.55,0.5,c.y); col+=vec3(0.05,0.06,0.08)*exp(-dot(c*vec2(1.0,3.5)+vec2(0.0,1.2),c*vec2(1.0,3.5)+vec2(0.0,1.2))*3.0);
  } else if(uScene==3){ // 场口：天光、远山、土坡
    float hz=0.06+0.03*sin(c.x*5.0)+0.025*vnoise(vec3(c.x*6.0,0.0,3.0)); vec3 sky=mix(vec3(0.62,0.60,0.52),vec3(0.36,0.46,0.58),smoothstep(0.0,0.5,c.y));
    vec3 gnd=mix(vec3(0.30,0.21,0.13),vec3(0.16,0.11,0.07),smoothstep(0.1,-0.5,c.y))*(0.85+0.3*vnoise(vec3(c*vec2(14.0,40.0),2.0)));
    col=mix(gnd,sky,smoothstep(hz-0.01,hz+0.012,c.y))*0.62; col=mix(col,vec3(0.34,0.33,0.30),(1.0-smoothstep(hz,hz+0.10,c.y))*step(hz,c.y)*0.55);
    col+=vec3(0.45,0.36,0.22)*exp(-dot(c-vec2(-0.5,0.42),c-vec2(-0.5,0.42))*6.0);
  }
  col=(col+vec3(0.012)*(vnoise(vec3(gl_FragCoord.xy*0.9,1.0))-0.5))*(0.30+0.70*uAmbient);
  vec3 p,n; float fl;
  if(trace(uCamPos,rd,p,n,fl)) col=shade(p,n,rd,detail,fl);
  if(uGlare.z>0.0){ float d=length(gl_FragCoord.xy-uGlare.xy)/uRes.y; col+=vec3(1.0,0.95,0.85)*uGlare.z*(0.020/(d*d+0.0012)+0.10*exp(-d*d*40.0)); }
  col=aces(col*1.15);
  col=pow(col,vec3(1.0/2.2));
  col+=(ign(gl_FragCoord.xy+17.0)-0.5)/255.0;
  col=mix(col,vec3(0.75,0.7,0.6),rim*0.9);
  outC=vec4(col,1.0);
}`;

/* 成品托盘：解析造型（手镯、牌子、平安扣、蛋面、珠串、摆件），玉质用体内步进：
 * 光折射进玉里，沿途被散射和吸收，薄处透亮、厚处沉，色根按扰动噪声呈絮状。 */
window.JADE_TRAY_FS = `#version 300 es
precision highp float;
uniform vec2 uRes; uniform vec3 uCamPos; uniform mat3 uCamRot; uniform float uTan; uniform vec2 uTray;
uniform int uN; uniform vec4 uIt[16]; uniform vec4 uIc[16]; uniform vec4 uIb[16]; uniform vec4 uIx[16];
out vec4 outC;
float hash(vec3 p){ p=fract(p*0.3183099+vec3(.1,.2,.3)); p*=17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
float vnoise(vec3 x){ vec3 i=floor(x), f=fract(x); f=f*f*(3.0-2.0*f);
  return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z); }
float fbm(vec3 p){ return 0.5*vnoise(p)+0.3*vnoise(p*2.1+3.1)+0.2*vnoise(p*4.3+7.7); }
float ign(vec2 p){ return fract(52.9829189*fract(dot(p,vec2(0.06711056,0.00583715)))); }
float smin(float a,float b,float k){ float h=clamp(0.5+0.5*(b-a)/k,0.,1.); return mix(b,a,h)-k*h*(1.-h); }
float sdRBox(vec3 p, vec3 b, float r){ vec3 d=abs(p)-b+r; return length(max(d,0.))+min(max(d.x,max(d.y,d.z)),0.)-r; }
float sdEll(vec3 p, vec3 r){ float k0=length(p/r), k1=length(p/(r*r)); return k0*(k0-1.0)/max(k1,1e-4); }
// 牌面浮雕高度（0..1）。th: 1 佛公 2 山水 3 花件
float motif(vec2 q, int th, float sd){
  if(th==1){
    float head=length(q-vec2(0.,-8.5))-4.6, body=length((q-vec2(0.,2.5))/vec2(1.0,0.86))-8.6;
    float ears=min(length(q-vec2(-5.0,-8.2)),length(q-vec2(5.0,-8.2)))-1.6;
    float d=min(min(head,body),ears); float h=smoothstep(0.6,-2.6,d);
    h+=0.35*smoothstep(1.2,-1.5,length(q-vec2(0.,3.5))-5.2);
    h-=0.22*smoothstep(0.45,0.0,abs(length(q-vec2(0.,-9.6))-2.4))*step(-9.0,q.y)*step(abs(q.x),2.1);
    h-=0.16*smoothstep(0.45,0.0,abs(length(q-vec2(0.,0.5))-7.2))*step(q.y,-1.0);
    return h; }
  if(th==2){ float h=0.0;
    for(int k=0;k<3;k++){ float fk=float(k); float ridge=-7.0+fk*6.0+2.8*sin(q.x*0.45+fk*2.1+sd)+1.4*sin(q.x*1.1+fk*4.0)+abs(q.x)*0.22;
      h=max(h,(0.95-0.28*fk)*smoothstep(0.0,1.4,q.y-ridge)*smoothstep(15.8,13.6,q.y)); }
    h=max(h,0.85*smoothstep(0.5,-0.6,length(q-vec2(5.5,-12.0))-2.3));
    h+=0.10*sin(q.y*2.4+sin(q.x*0.7))*smoothstep(11.5,13.5,q.y);
    return h; }
  if(th==3){ vec2 c=q-vec2(0.,-4.0); float a=atan(c.y,c.x), r=length(c);
    float h=0.9*smoothstep(0.8,-2.4,r-(5.2+2.6*cos(5.0*a)))*(0.72+0.28*cos(5.0*a)); h=max(h,1.0*smoothstep(0.4,-1.0,r-1.9));
    vec2 l1=(q-vec2(-4.2,8.5))*mat2(0.8,-0.6,0.6,0.8), l2=(q-vec2(4.6,10.0))*mat2(0.8,0.6,-0.6,0.8);
    h=max(h,0.6*smoothstep(0.5,-1.2,length(l1/vec2(1.0,0.42))-4.6)*(1.0-0.5*smoothstep(0.3,0.0,abs(l1.y))));
    h=max(h,0.6*smoothstep(0.5,-1.2,length(l2/vec2(1.0,0.42))-4.1)*(1.0-0.5*smoothstep(0.3,0.0,abs(l2.y))));
    h=max(h,0.45*smoothstep(0.7,0.0,abs(q.x-1.5*sin(q.y*0.5)))*step(1.5,q.y)*step(q.y,14.5)); return h; }
  return 0.0; }
float sdItem(vec3 p, int i){
  vec3 q=p-vec3(uIt[i].x,0.0,uIt[i].y); int t=int(uIt[i].z+0.5); float sd=uIt[i].w; int th=int(uIx[i].z+0.5);
  if(t==0){ vec2 c=vec2(length(q.xz)-31.0,(q.y-5.6)*0.94); return length(c)-5.4; }                 // 圆条手镯
  if(t==1){
    if(th==4){ return length(vec2(length(q.xz)-9.2,(q.y-3.1)*1.65))-5.0; }                           // 平安扣
    float b=sdRBox(q-vec3(0.0,3.0,0.0),vec3(12.0,3.0,18.0),2.6);
    float top=smoothstep(2.2,5.2,q.y)*smoothstep(0.0,2.2,-max(abs(q.x)-11.2,abs(q.z)-17.2));
    if(th==0){ b+=0.30*smoothstep(0.55,0.0,abs(max(abs(q.x)-9.2,abs(q.z)-15.2)))*top; return max(b,-(length(q.xz-vec2(0.0,-15.6))-1.2)); }
    return b-1.5*motif(q.xz,th,sd)*top; }
  if(t==2){ return max(sdEll(q,vec3(7.5,4.8,6.0)),-q.y); }                                           // 蛋面
  if(t==3){ float sa=6.2831853/18.0; float a=round(atan(q.z,q.x)/sa)*sa; return length(q-vec3(26.0*cos(a),4.4,26.0*sin(a)))-4.3; }
  // 摆件
  float d;
  if(th==1){ d=sdEll(q-vec3(0.0,12.0,0.0),vec3(14.0,12.5,11.5)); d=smin(d,length(q-vec3(0.0,29.0,1.0))-7.6,4.0);
    d=smin(d,min(length(q-vec3(-7.6,28.5,0.0)),length(q-vec3(7.6,28.5,0.0)))-2.6,1.6);
    d=smin(d,sdEll(q-vec3(0.0,10.0,7.5),vec3(9.0,8.0,6.5)),3.0);
    d=smin(d,min(sdEll(q-vec3(-12.5,13.0,4.0),vec3(4.0,7.0,4.5)),sdEll(q-vec3(12.5,13.0,4.0),vec3(4.0,7.0,4.5))),3.0);
    d+=0.35*smoothstep(0.5,0.0,abs(length(q.xy-vec2(0.0,30.0))-3.0))*step(q.y,29.4)*step(5.5,q.z); }
  else if(th==2){ d=sdEll(q-vec3(0.0,17.0,0.0),vec3(10.0,21.0,8.0)); d=smin(d,sdEll(q-vec3(-11.5,10.0,1.0),vec3(8.5,14.0,7.0)),5.0); d=smin(d,sdEll(q-vec3(10.5,8.0,-1.0),vec3(8.5,11.5,7.0)),5.0);
    d-=1.8*(fbm(vec3(q.x*0.5,q.y*0.14,q.z*0.5)+sd)-0.5)+0.5*sin(q.x*1.7+q.z*1.1+q.y*0.3); }
  else if(th==3){ d=length(q-vec3(0.0,11.0,0.0))-6.5; float sa=6.2831853/7.0; float a=atan(q.z,q.x); float ar=a-round(a/sa)*sa; float rr=length(q.xz);
    vec3 pq=vec3(rr*cos(ar),q.y,rr*sin(ar)); vec3 pp=pq-vec3(10.5,9.0,0.0); pp.xy=mat2(0.82,0.57,-0.57,0.82)*pp.xy;
    d=smin(d,sdEll(pp,vec3(3.2,10.5,5.2)),2.2); d=smin(d,sdEll(q-vec3(0.0,2.5,0.0),vec3(13.0,3.0,13.0)),3.0); }
  else { vec3 qc=q-vec3(0.0,19.0,0.0); d=(length(qc/vec3(17.0,20.0,12.0))-1.0)*12.0-3.2*(fbm(qc*0.11+sd)-0.5)+0.7*sin(qc.y*0.9+qc.x*0.5+3.0*fbm(qc*0.08+sd)); }
  return max(d*0.85,-q.y); }
float mapI(vec3 p, out int id){ float d=1e9; id=-1; for(int i=0;i<16;i++){ if(i>=uN) break; vec2 c=p.xz-uIt[i].xy; float far=length(c)-46.0; if(far>d) continue; float v=sdItem(p,i); if(v<d){ d=v; id=i; } } return d; }
float mapD(vec3 p){ int id; return mapI(p,id); }
vec3 nrm(vec3 p, int id){ const float e=0.12; vec2 k=vec2(1.,-1.); return normalize(k.xyy*sdItem(p+k.xyy*e,id)+k.yyx*sdItem(p+k.yyx*e,id)+k.yxy*sdItem(p+k.yxy*e,id)+k.xxx*sdItem(p+k.xxx*e,id)); }
float shadow(vec3 p, vec3 l){ float res=1.0, t=1.0; for(int i=0;i<16;i++){ float d=mapD(p+l*t); res=min(res,5.0*d/t); t+=clamp(d,0.8,6.0); if(res<0.03||t>70.0) break; } return clamp(res,0.0,1.0); }
vec3 env(vec3 r, vec3 L){ return vec3(1.0,0.97,0.92)*smoothstep(0.84,0.97,dot(r,L))*2.6+vec3(0.9,0.95,1.0)*smoothstep(0.88,0.98,dot(r,normalize(vec3(-0.5,0.7,-0.4))))*1.2+vec3(0.20,0.21,0.23)*smoothstep(-0.2,0.9,r.y)+vec3(0.10,0.08,0.06)*smoothstep(0.0,-0.6,r.y)+0.02; }
vec3 feltAt(vec2 xz){ return vec3(0.030,0.050,0.044)*(0.8+0.5*vnoise(vec3(xz*3.0,1.0)))+vec3(0.018)*vnoise(vec3(xz*0.05,3.0)); }
vec3 jade(vec3 p, vec3 n, vec3 rd, int id, vec3 L, float sh){
  float w=uIc[id].a, lv=uIb[id].a, sd=uIt[id].w, cot=uIx[id].y; vec3 body=uIb[id].rgb, band=uIc[id].rgb; vec3 org=vec3(uIt[id].x,0.0,uIt[id].y);
  float sig=0.85*exp(-4.4*w);                            // 每毫米散射：豆 0.55 很快不透，冰 0.05 半透，玻璃 0.013 几乎不散
  vec3 dir=refract(rd,n,1.0/1.55); if(dot(dir,dir)<0.5) dir=rd;
  vec3 L2=normalize(vec3(-0.5,0.30,-0.75));              // 背后的逆光，让薄处和边缘透亮
  vec3 T=vec3(1.0), acc=vec3(0.0); float dt=0.55; vec3 s=p-n*0.12+dir*dt*ign(gl_FragCoord.xy);
  float ndl=max(dot(n,L),0.0); bool exited=false; vec3 se=s;
  for(int k=0;k<20;k++){
    float d=sdItem(s,id); if(d>0.06&&k>1){ exited=true; break; }
    vec3 q=s-org;
    vec3 wq=q+2.6*(vec3(vnoise(q*0.20+sd),vnoise(q*0.20+sd+7.0),vnoise(q*0.20+sd+13.0))-0.5);   // 色根跟着扰动走，呈絮状
    float f=fbm(wq*0.085+sd)*0.72+0.28*vnoise(wq*0.33+sd*1.7);
    float mask=smoothstep(1.0-lv*1.06-0.10,1.0-lv*1.06+0.16,f+0.16*lv);
    vec3 alb=mix(body,band,mask*(0.62+0.38*lv));
    float cm=cot*smoothstep(0.58,0.80,fbm(q*0.35+sd+9.0)); alb=mix(alb,vec3(0.97),cm*0.8);
    float grain=(vnoise(q*2.4+sd)-0.5)*(1.0-w);
    float dep=max(0.0,-d);
    float l1=exp(-sig*dep*1.5)*(0.50+0.50*ndl)*(0.45+0.55*sh);
    float l2=exp(-sig*max(0.0,-sdItem(s+L2*2.5,id))*2.4)*0.60;
    vec3 Lin=(vec3(1.0,0.97,0.92)*l1+vec3(0.86,0.93,1.0)*l2)*0.80+0.04;
    float sc=sig*(1.0+0.7*grain)+cm*0.5;
    vec3 ab=(1.0-alb)*(0.05+0.22*mask*w);                 // 色越浓、路越长，颜色越沉
    acc+=T*alb*sc*dt*Lin; T*=exp(-(vec3(sc)+ab)*dt);
    s+=dir*dt; se=s; dt*=1.13;
  }
  vec3 behind=feltAt(se.xz)*2.0*(0.35+0.65*sh)+vec3(0.05,0.055,0.06)*smoothstep(-0.2,0.6,dot(dir,-L2));
  acc+=T*mix(body,band,lv*0.5)*behind*(exited?1.0:0.35);
  float ndv=max(dot(n,-rd),0.0); float F=0.045+0.955*pow(1.0-ndv,5.0);
  vec3 hv=normalize(L-rd); float nh=max(dot(n,hv),0.0);
  float sp=pow(nh,mix(70.0,520.0,w))*mix(0.55,2.4,w)*sh+pow(nh,9.0)*0.07*sh;   // 一点锐高光 + 一层柔润的油光
  return acc*0.92*(1.0-F)+env(reflect(rd,n),L)*F*mix(0.55,1.0,w)*mix(0.5,1.0,sh)+vec3(sp); }
vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/(0.5*uRes.y); vec3 rd=normalize(uCamRot*vec3(uv*uTan,-1.0)); vec3 ro=uCamPos;
  vec3 L=normalize(vec3(0.45,0.80,0.40)); vec3 col=vec3(0.02,0.018,0.016);
  float t=0.0, d=1e9; int id=-1; bool hit=false; float tg=rd.y<0.0?-ro.y/rd.y:1e9; float tmax=min(tg,2500.0);
  t=max(0.0,(ro.y-46.0)/max(1e-4,-rd.y)); if(rd.y>=0.0) t=tmax;
  for(int i=0;i<130;i++){ if(t>=tmax) break; d=mapI(ro+rd*t,id); if(d<0.02){ hit=true; break; } t+=d*0.85; }
  if(hit){ vec3 p=ro+rd*t, n=nrm(p,id); col=jade(p,n,rd,id,L,shadow(p+n*0.4,L)); }
  else if(tg<2400.0){
    vec3 p=ro+rd*tg; vec2 a=abs(p.xz)-uTray; float inT=1.0-smoothstep(-1.0,1.0,max(a.x,a.y)); float rimd=abs(max(a.x,a.y));
    vec3 wood=vec3(0.10,0.065,0.04)*(0.6+0.6*vnoise(vec3(p.x*0.02,p.z*0.4,5.0)));
    vec3 g=mix(wood,feltAt(p.xz),inT); g=mix(g,vec3(0.23,0.16,0.09),(1.0-smoothstep(0.0,3.0,rimd))*0.9);
    float sh=shadow(p+vec3(0.0,0.2,0.0),L); int ii; float near=mapI(p+vec3(0.0,2.0,0.0),ii); float ao=clamp(near/9.0,0.0,1.0);
    g*=(0.25+0.75*sh)*(0.45+0.55*ao)*1.7*max(L.y,0.0)+0.03;
    if(ii>=0){ float gl=exp(-max(near,0.0)*0.22)*uIc[ii].a*(0.4+0.6*sh); g+=mix(uIb[ii].rgb,uIc[ii].rgb,uIb[ii].a)*gl*0.05; }   // 通透的料把光染到绒布上
    for(int i=0;i<16;i++){ if(i>=uN) break; if(uIx[i].x>0.5){ float r=length(p.xz-uIt[i].xy); g+=vec3(0.9,0.65,0.25)*(smoothstep(41.0,42.5,r)-smoothstep(43.5,45.0,r))*0.8; } }
    col=g*exp(-tg*0.0007);
  }
  col=aces(col*1.05); col=pow(col,vec3(1.0/2.2)); col+=(ign(gl_FragCoord.xy)-0.5)/255.0;
  outC=vec4(col,1.0);
}`;
