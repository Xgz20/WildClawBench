/* Read-only native Calc observations; no scoring or document saving. */
import com.sun.star.beans.PropertyState;
import com.sun.star.beans.PropertyValue;
import com.sun.star.bridge.XUnoUrlResolver;
import com.sun.star.comp.helper.Bootstrap;
import com.sun.star.frame.XComponentLoader;
import com.sun.star.frame.XDesktop;
import com.sun.star.lang.XComponent;
import com.sun.star.sheet.XCalculatable;
import com.sun.star.sheet.XSpreadsheet;
import com.sun.star.sheet.XSpreadsheetDocument;
import com.sun.star.table.XCell;
import com.sun.star.text.XTextRange;
import com.sun.star.uno.UnoRuntime;
import com.sun.star.uno.XComponentContext;
import com.sun.star.util.XCloseable;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Properties;

public class NativeCalcObserve {
    static PropertyValue property(String name,Object value) {
        return new PropertyValue(name,-1,value,PropertyState.DIRECT_VALUE);
    }
    public static void main(String[] args) throws Exception {
        if(args.length<4)throw new IllegalArgumentException("connection, source URI, receipt and cells required");
        Properties result=new Properties();XDesktop desktop=null;XComponent component=null;int exit=2;
        try {
            XComponentContext local=Bootstrap.createInitialComponentContext((Map<String,Object>)null);
            XUnoUrlResolver resolver=UnoRuntime.queryInterface(XUnoUrlResolver.class,
                local.getServiceManager().createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver",local));
            Object remote=null;long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(60);
            while(System.nanoTime()<deadline) {
                try{remote=resolver.resolve(args[0]);break;}
                catch(com.sun.star.connection.NoConnectException error){Thread.sleep(100);}
            }
            if(remote==null)throw new IllegalStateException("native Calc connection unavailable");
            XComponentContext context=UnoRuntime.queryInterface(XComponentContext.class,remote);
            Object service=context.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop",context);
            desktop=UnoRuntime.queryInterface(XDesktop.class,service);
            XComponentLoader loader=UnoRuntime.queryInterface(XComponentLoader.class,service);
            component=loader.loadComponentFromURL(args[1],"_blank",0,new PropertyValue[]{
                property("Hidden",true),property("ReadOnly",true),property("MacroExecutionMode",(short)0),
                property("UpdateDocMode",(short)0)});
            XSpreadsheetDocument book=UnoRuntime.queryInterface(XSpreadsheetDocument.class,component);
            if(book==null)throw new IllegalStateException("not a native spreadsheet");
            UnoRuntime.queryInterface(XCalculatable.class,component).calculateAll();
            for(int i=3;i<args.length;i++) {
                String location=args[i];int split=location.lastIndexOf('!');
                if(split<1)throw new IllegalArgumentException("invalid cell location");
                String sheet=location.substring(0,split),address=location.substring(split+1);
                XSpreadsheet tab=UnoRuntime.queryInterface(XSpreadsheet.class,book.getSheets().getByName(sheet));
                XCell cell=tab.getCellRangeByName(address).getCellByPosition(0,0);
                String prefix="cell."+(i-3)+".";
                result.setProperty(prefix+"location",location);
                result.setProperty(prefix+"error",Integer.toString(cell.getError()));
                result.setProperty(prefix+"formula",cell.getFormula());
                result.setProperty(prefix+"display",UnoRuntime.queryInterface(XTextRange.class,cell).getString());
                result.setProperty(prefix+"value",Double.toString(cell.getValue()));
                result.setProperty(prefix+"type",cell.getType().toString());
            }
            result.setProperty("cell_count",Integer.toString(args.length-3));
            result.setProperty("read_only","true");result.setProperty("saved","false");
            result.setProperty("macro_execution","NEVER_EXECUTE");result.setProperty("external_link_updates","NO_UPDATE");
            result.setProperty("status","pass");exit=0;
        } catch(Exception error) {
            result.setProperty("status","evaluator_error");result.setProperty("error",error.toString());
        } finally {
            if(component!=null)try{UnoRuntime.queryInterface(XCloseable.class,component).close(true);}catch(Exception ignored){}
            if(desktop!=null)try{desktop.terminate();}catch(Exception ignored){}
            try(var writer=Files.newBufferedWriter(Path.of(args[2]),StandardCharsets.UTF_8)){result.store(writer,"native Calc observation");}
        }
        System.exit(exit);
    }
}
