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

import java.util.Map;
import static net.bytebuddy.matcher.ElementMatchers.any;

public class ReturnPerturbationStrategy implements PerturbationStrategy {

    @Override
    public DynamicType.Builder<?> apply(DynamicType.Builder<?> builder, TypeDescription typeDesc, ClassLoader classLoader, Map<String, AsmMethodAnalyser.MethodLineInfo> lineInfoMap) {
        return builder.visit(
                new AsmVisitorWrapper.ForDeclaredMethods()
                        .invokable(any(), new ReturnPerturberWrapper())
                        .writerFlags(net.bytebuddy.jar.asm.ClassWriter.COMPUTE_FRAMES)
        );
    }

    public static class ReturnPerturberWrapper implements AsmVisitorWrapper.ForDeclaredMethods.MethodVisitorWrapper {
        @Override
        public MethodVisitor wrap(TypeDescription instrumentedType, MethodDescription instrumentedMethod, MethodVisitor methodVisitor, Implementation.Context implementationContext, TypePool typePool, int writerFlags, int readerFlags) {

            if (!InstrumentationFilters.isTargetMethod(instrumentedMethod, instrumentedType)) {
                return methodVisitor;
            }

            TypeDescription.Generic retType = instrumentedMethod.getReturnType();
            if (!ProbeRegistrar.isSupportedType(retType)) {
                return methodVisitor;
            }

            boolean isBooleanReturn = retType.represents(boolean.class);
            String returnInternalName = retType.asErasure().getInternalName();
            String typeName = ProbeRegistrar.resolveTypeName(retType);

            return new ReturnVisitor(Opcodes.ASM9, methodVisitor, instrumentedMethod.toString(), instrumentedMethod.getDescriptor(), typeName, returnInternalName, isBooleanReturn);
        }
    }

    public static class ReturnVisitor extends MethodVisitor {
        private final String methodSignature;
        private final String asmDesc;
        private final String typeName;
        private final String returnInternalName;
        private final boolean isBooleanReturn;
        private int currentLine = -1;

        public ReturnVisitor(int api, MethodVisitor methodVisitor, String methodSignature, String asmDesc, String typeName, String returnInternalName, boolean isBooleanReturn) {
            super(api, methodVisitor);
            this.methodSignature = methodSignature;
            this.asmDesc = asmDesc;
            this.typeName = typeName;
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
            if (opcode == Opcodes.IRETURN || opcode == Opcodes.ARETURN) {
                int probeId = ProbeRegistrar.registerReturn(methodSignature, currentLine, asmDesc, typeName);

                if (opcode == Opcodes.IRETURN) {
                    super.visitLdcInsn(probeId);
                    if (isBooleanReturn) {
                        super.visitMethodInsn(Opcodes.INVOKESTATIC, PerturbationStrategy.GATE_CLASS, PerturbationStrategy.GATE_METHOD, PerturbationStrategy.DESC_BOOL, false);
                    } else {
                        super.visitMethodInsn(Opcodes.INVOKESTATIC, PerturbationStrategy.GATE_CLASS, PerturbationStrategy.GATE_METHOD, PerturbationStrategy.DESC_INT, false);
                    }
                } else {
                    super.visitLdcInsn(probeId);
                    super.visitMethodInsn(Opcodes.INVOKESTATIC, PerturbationStrategy.GATE_CLASS, PerturbationStrategy.GATE_METHOD, PerturbationStrategy.DESC_OBJ, false);
                    super.visitTypeInsn(Opcodes.CHECKCAST, returnInternalName);
                }
            }
            super.visitInsn(opcode);
        }
    }
}