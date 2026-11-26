import java.io.File;
import java.util.*;
import com.cburch.logisim.file.*;
import com.cburch.logisim.proj.Project;
import com.cburch.logisim.circuit.*;
import com.cburch.logisim.comp.Component;
import com.cburch.logisim.data.*;
import com.cburch.logisim.instance.*;
import com.cburch.logisim.std.wiring.Pin;
import java.lang.reflect.Method;

public class NativeSystemCheck {
    static Component pin(Circuit c, String name) {
        for (Component comp : c.getNonWires()) {
            Attribute attr = comp.getAttributeSet().getAttribute("label");
            if (attr != null && name.equals(comp.getAttributeSet().getValue(attr))
                    && comp.getFactory() instanceof Pin) return comp;
        }
        throw new AssertionError("Missing pin: " + name);
    }
    static void put(CircuitState s, String name, int value) {
        Component c = pin(s.getCircuit(), name);
        InstanceState i = s.getInstanceState(c);
        int width = ((Value)((Pin)c.getFactory()).getValue(i)).getWidth();
        ((Pin)c.getFactory()).setValue(i, Value.createKnown(BitWidth.create(width), value));
        s.markComponentAsDirty(c);
    }
    static int get(CircuitState s, String name) {
        Component c = pin(s.getCircuit(), name);
        Value v = ((Pin)c.getFactory()).getValue(s.getInstanceState(c));
        if (!v.isFullyDefined()) throw new AssertionError(name + " undefined: " + v);
        return v.toIntValue();
    }
    static int net(CircuitState state, String label) {
        for (Component component : state.getCircuit().getNonWires()) {
            Attribute attr = component.getAttributeSet().getAttribute("label");
            if (component.getFactory().getName().equals("Tunnel") && attr != null
                    && label.equals(component.getAttributeSet().getValue(attr))) {
                Value value = state.getValue(component.getLocation());
                if (!value.isFullyDefined()) throw new AssertionError("Undefined net " + label);
                return value.toIntValue();
            }
        }
        throw new AssertionError("Missing net " + label);
    }
    static void eq(String label, int expected, int actual) {
        if (expected != actual) throw new AssertionError(label + " expected "
            + Integer.toHexString(expected) + " actual " + Integer.toHexString(actual));
    }
    public static void main(String[] args) {
        try {
            File path = new File(args[0]);
            if (!path.isFile()) throw new AssertionError("Missing SnakeSystem.circ");
            LogisimFile file = new Loader(null).openLogisimFile(path);
            Project project = new Project(file);
            CircuitState bus = new CircuitState(project, file.getCircuit("SnakeBus"));
            bus.getPropagator().propagate();
            int[][] vectors = {
                {0,1,1,0,0x55,0}, {0xffc,1,1,0,0x55,31},
                {0x1000,0,0,0,2,0}, {0x1004,1,0,1,2,1},
                {0x1008,1,0,1,2,2}, {0x1040,1,0,1,2,16},
                {0x107c,1,0,1,2,31}, {0x1080,1,0,0,0,0},
                {0x2000,1,0,0,0,0}, {-4096,1,0,0,0,0},
                {0x1001,1,0,0,0,0}
            };
            for (int[] v : vectors) {
                put(bus,"addr",v[0]); put(bus,"memwrite",v[1]);
                put(bus,"ramdata",0x55); put(bus,"iodata",2);
                bus.getPropagator().propagate();
                eq("RAM write "+v[0],v[2],get(bus,"ramwrite"));
                eq("IO write "+v[0],v[3],get(bus,"iowrite"));
                eq("read "+v[0],v[4],get(bus,"readdata"));
                if (v[0]>=0 && v[0]<=0x107c)
                    eq("word index",v[5],get(bus,"index"));
            }
            System.out.println("PASS SnakeBus: " + vectors.length + " address/write/read vectors");
            CircuitState cpu = new CircuitState(project, file.getMainCircuit());
            cpu.getPropagator().propagate();
            int[][] expectedWrites = {{1,2},{2,1},{3,2},{4,0x188},{16,1},{31,0x8000}};
            int writes = 0;
            for(int i=0;i<800;i++) {
                if (net(cpu,"CLK")==0 && net(cpu,"SNAKE_IO_WR")==1) {
                    if (writes >= expectedWrites.length) throw new AssertionError("Extra MMIO write");
                    eq("write index "+writes,expectedWrites[writes][0],net(cpu,"SNAKE_INDEX"));
                    eq("write data "+writes,expectedWrites[writes][1],net(cpu,"MDin"));
                    writes++;
                }
                cpu.getPropagator().tick(); cpu.getPropagator().propagate();

            }
            eq("observed MMIO write count",6,writes);
            eq("smoke result",0x600d,get(cpu,"A_RESULT"));
            eq("event read",2,get(cpu,"A_EVENTS"));
            eq("RAM zero sentinel",0x55,get(cpu,"A_RAM0"));
            eq("RAM alias sentinel",0x66,get(cpu,"A_RAM8"));
            eq("MMIO consecutive writes",6,get(cpu,"A_WRITE_COUNT"));
            eq("last write index",31,get(cpu,"A_LAST_INDEX"));
            eq("last write value",0x8000,get(cpu,"A_LAST_DATA"));
            Component ram = null;
            for (Component component : cpu.getCircuit().getNonWires())
                if (component.getFactory().getName().equals("RAM")) ram = component;
            Object ramState = cpu.getData(ram);
            Method contentsMethod = ramState.getClass().getMethod("getContents");
            contentsMethod.setAccessible(true);
            Object memory = contentsMethod.invoke(ramState);
            Method read = memory.getClass().getMethod("get",long.class);
            read.setAccessible(true);
            eq("actual RAM sentinel at byte 0",0x55,((Integer)read.invoke(memory,(long)(0))));
            eq("actual RAM sentinel at byte 8",0x66,((Integer)read.invoke(memory,(long)(2))));
            eq("stored EVENTS",2,((Integer)read.invoke(memory,(long)(0x500/4))));
            eq("stored status",0x600d,((Integer)read.invoke(memory,(long)(0x50c/4))));
            System.out.println("PASS CPU: smoke ROM, RAM isolation, 6 writes, result 0x600d");
            System.exit(0);
        } catch (Throwable error) {
            error.printStackTrace();
            System.exit(1);
        }
    }
}
