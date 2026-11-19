import test from 'node:test';
import assert from 'node:assert/strict';
import {loadInventory,chooseTake,chooseListener,currentInventory} from '../frontend/src/nativeAuditionSelection.js';
const A={take_id:'first',listeners:['/Camera','/Actor']};
const B={take_id:'second',listeners:['/Other']};
const C={take_id:'silent',listeners:[]};
const bridge={};
const original=()=>loadInventory([A,B,C],'movie',bridge,1);
test('catalog arrival atomically selects first exact Take and listener',()=>{
 const s=original(); assert.equal(s.takeId,'first');assert.equal(s.listener,'/Camera');
});
test('switch resets listener to that Take, never previous listener',()=>{
 let s=chooseListener(original(),'/Actor');assert.equal(s.listener,'/Actor');
 s=chooseTake(s,'second');assert.equal(s.takeId,'second');assert.equal(s.listener,'/Other');
});
test('reject listener not belonging to current Take',()=>{
 assert.equal(chooseListener(chooseTake(original(),'second'),'/Actor').listener,'');
});
test('empty or unknown Take has no listener',()=>{
 assert.equal(chooseTake(original(),'silent').listener,'');assert.equal(chooseTake(original(),'missing').takeId,'');
 assert.equal(loadInventory([],'movie',bridge,1).listener,'');
});
test('project, native bridge and capture revision changes invalidate stale inventory',()=>{
 for(const args of [['other',bridge,1],['movie',{},1],['movie',bridge,2]]){
   const s=currentInventory(original(),...args);assert.deepEqual(s.takes,[]);assert.equal(s.takeId,'');assert.equal(s.listener,'');
 }
 assert.equal(currentInventory(original(),'movie',bridge,1).listener,'/Camera');
});
