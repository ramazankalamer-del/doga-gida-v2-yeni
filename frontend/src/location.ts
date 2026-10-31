export function captureLocation(geolocation:Pick<Geolocation,'getCurrentPosition'>|undefined,secure:boolean):Promise<{latitude:string;longitude:string;accuracy:number|null}>{
 if(!secure)return Promise.reject(new Error('Konum almak için HTTPS veya bu bilgisayarda localhost bağlantısı kullanın.'));
 if(!geolocation)return Promise.reject(new Error('Bu tarayıcı konum almayı desteklemiyor. Koordinatları elle girebilirsiniz.'));
 return new Promise((resolve,reject)=>{
  geolocation.getCurrentPosition(position=>{
   const {latitude,longitude,accuracy}=position.coords;
   if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180){reject(new Error('Cihaz geçerli koordinat döndürmedi. Elle giriş yapabilir veya tekrar deneyebilirsiniz.'));return;}
   resolve({latitude:latitude.toFixed(6),longitude:longitude.toFixed(6),accuracy:Number.isFinite(accuracy)&&accuracy>=0?Math.ceil(accuracy):null});
  },failure=>reject(new Error(failure.code===1?'Konum izni verilmedi. Tarayıcıdan izin verebilir veya koordinatları elle girebilirsiniz.':failure.code===3?'Konum alma zaman aşımına uğradı. Tekrar deneyin veya elle girin.':'Cihaz konumu bulunamadı. Tekrar deneyin veya elle girin.')),
  {enableHighAccuracy:true,timeout:10000,maximumAge:0});
 });
}
