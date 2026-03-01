package org.instrumentation;

import net.bytebuddy.asm.Advice;
import net.bytebuddy.dynamic.DynamicType;
import net.bytebuddy.implementation.bytecode.assign.Assigner;
import org.probe.PerturbationGate;
import org.probe.ProbeCatalog;

import static net.bytebuddy.matcher.ElementMatchers.returns;
import static net.bytebuddy.matcher.ElementMatchers.isSubTypeOf;

public class ReturnPerturbationStrategy implements PerturbationStrategy {

    @Override
    public DynamicType.Builder<?> apply(DynamicType.Builder<?> builder) {
        return builder
                .visit(Advice.to(IntegerAdvice.class).on(returns(int.class)))
                .visit(Advice.to(BooleanAdvice.class).on(returns(boolean.class)))
                .visit(Advice.to(ObjectAdvice.class).on(returns(isSubTypeOf(Object.class))));
    }

    public static int resolveProbe(String locationKey, String type) {
        int probeId = ProbeCatalog.idForLocation(locationKey);
        if (probeId != -1) {
            ProbeCatalog.describe(probeId, "Modified " + type + " return value in " + locationKey);
        }
        return probeId;
    }

    public static int perturbInt(int returnValue, String locationKey) {
        int probeId = resolveProbe(locationKey, "int");
        if (probeId != -1) {
            return PerturbationGate.apply(returnValue, probeId);
        }
        return returnValue;
    }

    public static boolean perturbBoolean(boolean returnValue, String locationKey) {
        int probeId = resolveProbe(locationKey, "boolean");
        if (probeId != -1) {
            return PerturbationGate.apply(returnValue, probeId);
        }
        return returnValue;
    }

    public static Object perturbObject(Object returnValue, String locationKey) {
        if (returnValue != null) {
            int probeId = resolveProbe(locationKey, "Object");
            if (probeId != -1) {
                return PerturbationGate.apply(returnValue, probeId);
            }
        }
        return returnValue;
    }

    public static class IntegerAdvice {
        @Advice.OnMethodExit
        public static void exit(@Advice.Return(readOnly = false) int returnValue,
                                @Advice.Origin String locationKey) {
            returnValue = ReturnPerturbationStrategy.perturbInt(returnValue, locationKey);
        }
    }

    public static class BooleanAdvice {
        @Advice.OnMethodExit
        public static void exit(@Advice.Return(readOnly = false) boolean returnValue,
                                @Advice.Origin String locationKey) {
            returnValue = ReturnPerturbationStrategy.perturbBoolean(returnValue, locationKey);
        }
    }

    public static class ObjectAdvice {
        @Advice.OnMethodExit
        public static void exit(@Advice.Return(readOnly = false, typing = Assigner.Typing.DYNAMIC) Object returnValue,
                                @Advice.Origin String locationKey) {
            returnValue = ReturnPerturbationStrategy.perturbObject(returnValue, locationKey);
        }
    }
}