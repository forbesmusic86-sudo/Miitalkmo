.arm
.align 4

.global test_asm
.type test_asm, %function

test_asm:
    mov r0, #0x1
    bx lr
