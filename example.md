## Input Sample
<div style="font-family: 'Courier New';">
<p> JCSY:CA0984/02SEP/LAX,I                                                         </p>
<p>FLT/ORIG   ARVL   BKD     CHK        UCK     NBRD       BAG                     </p>
<p>AA0352 /CLT       000/003 000/003+00 000/000 000/000+00 002/0032                </p>
<p>AA1012 /CLT       000/001 000/001+00 000/000 000/000+00 002/0036                               </p>
<p>AA1162 /DCA       000/001 000/001+00 000/000 000/000+00 000/0000  </p>
<p>AA1362 /PHX       000/001</p>
<p>##TOTAL##         004/022 004/021+00 000/001 000/000+00 023/0395   </p>
</div>

## Output Sample
<div style="font-family: 'Courier New';">
<p>JCSY:CA0984/02SEP/LAX,I                                                         </p>
<p>FLT/ORIG   ARVL   BKD     CHK        UCK     NBRD       BAG                     </p>
<p>AA0352 /CLT 15:02 000/003 000/003+00 000/000 000/000+00 002/0032                </p>
<p>AA1012 /CLT 19:27 000/001 000/001+00 000/000 000/000+00 002/0036                               </p>
<p>AA1162 /DCA 20:25 000/001 000/001+00 000/000 000/000+00 000/0000  </p>
<p>AA1362 /PHX 15:16 000/001</p>
<p>##TOTAL##         004/022 004/021+00 000/001 000/000+00 023/0395   </p>
</div>