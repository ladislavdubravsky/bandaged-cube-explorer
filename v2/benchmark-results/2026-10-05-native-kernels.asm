Native release benchmark, Rust 1.98.1 / LLVM 22.1.8, Intel i7-7500U.
LegacySparse and Tuned are identical; LLVM retained the sparse kernel as tuned_u.
These are fixed-U inspection probes, not retired-instruction counters.

axis_u: 23 static instructions including ret
   261b0:	c4 e1 f9 6e c7       	vmovq  %rdi,%xmm0
   261b5:	c4 e2 7d 59 c0       	vpbroadcastq %xmm0,%ymm0
   261ba:	c5 f1 73 f0 0f       	vpsllq $0xf,%xmm0,%xmm1
   261bf:	c5 f9 6c c9          	vpunpcklqdq %xmm1,%xmm0,%xmm1
   261c3:	c4 e3 7d 38 c9 01    	vinserti128 $0x1,%xmm1,%ymm0,%ymm1
   261c9:	c4 e2 f5 45 0d ae 50 	vpsrlvq -0x1af52(%rip),%ymm1,%ymm1        # b280 <GCC_except_table151+0xce0>
   261d2:	c4 e2 fd 45 15 c5 50 	vpsrlvq -0x1af3b(%rip),%ymm0,%ymm2        # b2a0 <GCC_except_table151+0xd00>
   261db:	c5 f5 db 0d 9d 4b fe 	vpand  -0x1b463(%rip),%ymm1,%ymm1        # ad80 <GCC_except_table151+0x7e0>
   261e3:	c5 ed db 15 b5 4d fe 	vpand  -0x1b24b(%rip),%ymm2,%ymm2        # afa0 <GCC_except_table151+0xa00>
   261eb:	c4 e2 fd 47 05 ac 47 	vpsllvq -0x1b854(%rip),%ymm0,%ymm0        # a9a0 <GCC_except_table151+0x400>
   261f4:	c5 fd db 05 24 4b fe 	vpand  -0x1b4dc(%rip),%ymm0,%ymm0        # ad20 <GCC_except_table151+0x780>
   261fc:	c5 ed eb c0          	vpor   %ymm0,%ymm2,%ymm0
   26200:	c5 fd eb c1          	vpor   %ymm1,%ymm0,%ymm0
   26204:	81 e7 00 00 10 00    	and    $0x100000,%edi
   2620a:	48 c1 e7 15          	shl    $0x15,%rdi
   2620e:	c4 e3 7d 39 c1 01    	vextracti128 $0x1,%ymm0,%xmm1
   26214:	c5 f9 eb c1          	vpor   %xmm1,%xmm0,%xmm0
   26218:	c5 f9 70 c8 ee       	vpshufd $0xee,%xmm0,%xmm1
   2621d:	c5 f9 eb c1          	vpor   %xmm1,%xmm0,%xmm0
   26221:	c4 e1 f9 7e c0       	vmovq  %xmm0,%rax
   26226:	48 09 f8             	or     %rdi,%rax
   26229:	c5 f8 77             	vzeroupper
   2622c:	c3                   	ret

tuned_u: 12 static instructions including ret
   26230:	48 89 f8             	mov    %rdi,%rax
   26233:	48 c1 e8 02          	shr    $0x2,%rax
   26237:	48 b9 15 00 a8 00 00 	movabs $0x540000a80015,%rcx
   26241:	48 21 c1             	and    %rax,%rcx
   26244:	48 ba aa ff 57 fd ef 	movabs $0x910eabeffd57ffaa,%rdx
   2624e:	48 21 fa             	and    %rdi,%rdx
   26251:	48 09 ca             	or     %rcx,%rdx
   26254:	48 c1 e7 06          	shl    $0x6,%rdi
   26258:	48 b8 40 00 00 02 00 	movabs $0x1000002000040,%rax
   26262:	48 21 f8             	and    %rdi,%rax
   26265:	48 09 d0             	or     %rdx,%rax
   26268:	c3                   	ret

axis_u_legal: 3 static instructions including ret
   220f0:	48 c1 e7 37          	shl    $0x37,%rdi
   220f4:	0f 94 c0             	sete   %al
   220f7:	c3                   	ret

legacy_u_legal: 4 static instructions including ret
   22100:	48 b8 02 0e 02 01 00 	movabs $0x8104000001020e02,%rax
   2210a:	48 85 c7             	test   %rax,%rdi
   2210d:	0f 94 c0             	sete   %al
   22110:	c3                   	ret
