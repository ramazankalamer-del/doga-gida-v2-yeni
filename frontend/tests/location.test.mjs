import {test} from 'node:test';
import assert from 'node:assert/strict';
import {captureLocation} from '../src/location.ts';

test('one-shot capture rounds coordinates and requests a fresh high-accuracy fix',async()=>{
 let calls=0;
 const geo={getCurrentPosition(success,failure,options){calls++;assert.deepEqual(options,{enableHighAccuracy:true,timeout:10000,maximumAge:0});success({coords:{latitude:41.00821234,longitude:28.97845678,accuracy:8.3}});}};
 assert.equal(calls,0);
 assert.deepEqual(await captureLocation(geo,true),{latitude:'41.008212',longitude:'28.978457',accuracy:9});
 assert.equal(calls,1);
});
test('unsupported or insecure contexts never request a location',async()=>{
 let called=false;const geo={getCurrentPosition(){called=true;}};
 await assert.rejects(captureLocation(geo,false),/HTTPS/);
 await assert.rejects(captureLocation(undefined,true),/desteklemiyor/);
 assert.equal(called,false);
});
for(const [code,message] of [[1,/izni verilmedi/],[2,/bulunamadı/],[3,/zaman aşımı/]]){
 test(`geolocation error ${code} explains manual fallback`,async()=>{
  await assert.rejects(captureLocation({getCurrentPosition(success,failure){failure({code});}},true),message);
 });
}
test('invalid coordinates and synchronous errors fail without saving',async()=>{
 await assert.rejects(captureLocation({getCurrentPosition(success){success({coords:{latitude:NaN,longitude:29,accuracy:1}});}},true),/geçerli koordinat/);
 await assert.rejects(captureLocation({getCurrentPosition(){throw new Error('cihaz hatası');}},true),/cihaz hatası/);
});
