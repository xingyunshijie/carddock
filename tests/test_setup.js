const assert=require('node:assert/strict');
const {buildConfig}=require('../setup.js');
const sample={image:'carddock:0.12.0-beta.1',source:'/mnt/cards',primary:'/volume1/media',backup:'/volume2/media',state:'/volume1/state',extra:'/volume3/media',uid:'1000',gid:'100',port:'18080',key:'a'.repeat(64)};
const c=buildConfig(sample).services.carddock;
assert.equal(c.environment.TARGET_ROOTS,'/destinations/primary:/destinations/backup:/storage/area1');
assert.equal(c.volumes[0].read_only,true);assert.equal(c.volumes[0].bind.propagation,'rslave');assert.equal(c.user,'1000:100');
for(const changes of [{primary:'/mnt/cards/sub'},{state:'/volume1/media/state'},{uid:'0'},{port:'70000'},{extra:'/volume1'},{source:'/mnt/cards/..'},{primary:'/volume1/$HOME'}])assert.throws(()=>buildConfig({...sample,...changes}));
assert.equal(buildConfig({...sample,backup:'',extra:''}).services.carddock.environment.TARGET_ROOTS,'/destinations/primary');
console.log('Offline installer configuration tests passed');
