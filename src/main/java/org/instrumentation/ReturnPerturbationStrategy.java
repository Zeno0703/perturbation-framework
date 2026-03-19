package org.instrumentation;

import net.bytebuddy.asm.AsmVisitorWrapper;
import net.bytebuddy.description.method.MethodDescription;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.dynamic.DynamicType;
import net.bytebuddy.implementation.Implementation;
import net.bytebuddy.jar.asm.Label;
import net.bytebuddy.jar.asm.MethodVisitor;
import net.bytebuddy.jar.asm.Opcodes;
import net.bytebuddy.pool.TypePool;
import org.probe.ProbeCatalog;

import static net.bytebuddy.matcher.ElementMatchers.any;

public class ReturnPerturbationStrategy implements PerturbationStrategy {

    @Override
    public DynamicType.Builder<?> apply(DynamicType.Builder<?> builder) {
        return builder.visit(
                new AsmVisitorWrapper.ForDeclaredMethods()
                        .method(any(), new ReturnPerturberWrapper())
                        .writerFlags(net.bytebuddy.jar.asm.ClassWriter.COMPUTE_FRAMES)
        );
    }

    public static class ReturnPerturberWrapper implements AsmVisitorWrapper.ForDeclaredMethods.MethodVisitorWrapper {
        @Override
        public MethodVisitor wrap(TypeDescription instrumentedType, MethodDescription instrumentedMethod, MethodVisitor methodVisitor, Implementation.Context implementationContext, TypePool typePool, int writerFlags, int readerFlags) {
            if (instrumentedMethod.isSynthetic() || instrumentedMethod.isBridge() || instrumentedMethod.getName().contains("$") || instrumentedMethod.getReturnType().represents(void.class)) {
                return methodVisitor;
            }
            if (instrumentedType.isEnum() && (instrumentedMethod.getName().equals("values") || instrumentedMethod.getName().equals("valueOf"))) {
                return methodVisitor;
            }

            TypeDescription.Generic retType = instrumentedMethod.getReturnType();
            if (retType.represents(long.class) || retType.represents(float.class) || retType.represents(double.class)) {
                return methodVisitor;
            }

            boolean isBooleanReturn = retType.represents(boolean.class);
            String returnInternalName = retType.asErasure().getInternalName();

            return new ReturnVisitor(Opcodes.ASM9, methodVisitor, instrumentedMethod.toString(), returnInternalName, isBooleanReturn);
        }
    }

    public static class ReturnVisitor extends MethodVisitor {
        private final String methodSignature;
        private final String returnInternalName;
        private final boolean isBooleanReturn;
        private int currentLine = -1;

        public ReturnVisitor(int api, MethodVisitor methodVisitor, String methodSignature, String returnInternalName, boolean isBooleanReturn) {
            super(api, methodVisitor);
            this.methodSignature = methodSignature;
            this.returnInternalName = returnInternalName;
            this.isBooleanReturn = isBooleanReturn;
        }

        @Override
        public void visitLineNumber(int line, Label start) {
            currentLine = line;
            super.visitLineNumber(line, start);
        }

        @Override
        public void visitInsn(int opcode) {
            if (opcode >= Opcodes.IRETURN && opcode <= Opcodes.ARETURN) {
                int probeId = resolveProbe(methodSignature, currentLine);

                if (probeId != -1) {
                    if (opcode == Opcodes.IRETURN) {
                        super.visitLdcInsn(probeId);
                        if (isBooleanReturn) {
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, "org/probe/PerturbationGate", "apply", "(ZI)Z", false);
                        } else {
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, "org/probe/PerturbationGate", "apply", "(II)I", false);
                        }
                    } else if (opcode == Opcodes.ARETURN) {
                        super.visitLdcInsn(probeId);
                        super.visitMethodInsn(Opcodes.INVOKESTATIC, "org/probe/PerturbationGate", "apply", "(Ljava/lang/Object;I)Ljava/lang/Object;", false);
                        super.visitTypeInsn(Opcodes.CHECKCAST, returnInternalName);
                    }
                }
            }
            super.visitInsn(opcode);
        }

        private int resolveProbe(String locationKey, int line) {
            int id = ProbeCatalog.idForLocation(locationKey + ":return:" + line);
            if (id == -1) {
                id = ProbeCatalog.idForLocation(locationKey + ":return");
            }
            return id;
        }
    }
}