/* Bulk read-only native Calc evaluation. Never sets or saves document cells. */
import com.sun.star.beans.PropertyState;
import com.sun.star.beans.PropertyValue;
import com.sun.star.bridge.XUnoUrlResolver;
import com.sun.star.comp.helper.Bootstrap;
import com.sun.star.frame.XComponentLoader;
import com.sun.star.frame.XDesktop;
import com.sun.star.lang.XComponent;
import com.sun.star.sheet.XCalculatable;
import com.sun.star.sheet.XCellRangeData;
import com.sun.star.sheet.XCellRangesQuery;
import com.sun.star.sheet.XSpreadsheet;
import com.sun.star.sheet.XSpreadsheetDocument;
import com.sun.star.table.CellRangeAddress;
import com.sun.star.table.XCell;
import com.sun.star.table.XCellRange;
import com.sun.star.text.XTextRange;
import com.sun.star.uno.UnoRuntime;
import com.sun.star.uno.XComponentContext;
import com.sun.star.util.XCloseable;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

public class NativeCalcValues {
    static PropertyValue property(String n,Object v){return new PropertyValue(n,-1,v,PropertyState.DIRECT_VALUE);}
    static String quoted(String text){
        if(text.length()>32767)throw new IllegalArgumentException("cell text exceeds Excel limit");
        StringBuilder b=new StringBuilder("\"");
        for(char c:text.toCharArray()){
            if(c=='"'||c=='\\')b.append('\\').append(c);
            else if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);
        }
        return b.append('"').toString();
    }
    static int[] coordinate(String address){
        if(!address.matches("[A-Z]{1,3}[1-9][0-9]{0,6}"))throw new IllegalArgumentException("coordinate");
        int i=0,column=0;while(i<address.length()&&Character.isLetter(address.charAt(i)))column=column*26+address.charAt(i++)-'A'+1;
        int row=Integer.parseInt(address.substring(i));
        if(column>16384||row>1048576)throw new IllegalArgumentException("coordinate bounds");
        return new int[]{column-1,row-1};
    }
    public static void main(String[] args) throws Exception {
        if(args.length!=5)throw new IllegalArgumentException("connection, source, receipt, request and output required");
        Properties receipt=new Properties();XDesktop desktop=null;XComponent component=null;int exit=2;
        try {
            List<String> requested=Files.readAllLines(Path.of(args[3]),StandardCharsets.UTF_8);
            if(requested.isEmpty()||requested.size()>100000||new HashSet<>(requested).size()!=requested.size())throw new IllegalArgumentException("request scope");
            Map<String,List<String>> grouped=new LinkedHashMap<>();
            for(String location:requested){int split=location.lastIndexOf('!');if(split<1)throw new IllegalArgumentException("location");
                coordinate(location.substring(split+1));grouped.computeIfAbsent(location.substring(0,split),k->new ArrayList<>()).add(location);}
            XComponentContext local=Bootstrap.createInitialComponentContext((Map<String,Object>)null);
            XUnoUrlResolver resolver=UnoRuntime.queryInterface(XUnoUrlResolver.class,
                local.getServiceManager().createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver",local));
            Object remote=null;long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(60);
            while(System.nanoTime()<deadline){try{remote=resolver.resolve(args[0]);break;}catch(com.sun.star.connection.NoConnectException e){Thread.sleep(100);}}
            if(remote==null)throw new IllegalStateException("native Calc unavailable");
            XComponentContext context=UnoRuntime.queryInterface(XComponentContext.class,remote);
            Object service=context.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop",context);
            desktop=UnoRuntime.queryInterface(XDesktop.class,service);
            component=UnoRuntime.queryInterface(XComponentLoader.class,service).loadComponentFromURL(args[1],"_blank",0,
                new PropertyValue[]{property("Hidden",true),property("ReadOnly",true),property("MacroExecutionMode",(short)0),property("UpdateDocMode",(short)0)});
            XSpreadsheetDocument book=UnoRuntime.queryInterface(XSpreadsheetDocument.class,component);
            if(book==null)throw new IllegalStateException("not a spreadsheet");
            UnoRuntime.queryInterface(XCalculatable.class,component).calculateAll();
            int count=0;long boundingCells=0;
            try(var writer=Files.newBufferedWriter(Path.of(args[4]),StandardCharsets.UTF_8)){
                for(var entry:grouped.entrySet()){
                    XSpreadsheet sheet=UnoRuntime.queryInterface(XSpreadsheet.class,book.getSheets().getByName(entry.getKey()));
                    int left=16383,right=0,top=1048575,bottom=0;
                    Map<String,int[]> coords=new LinkedHashMap<>();
                    for(String location:entry.getValue()){int[] p=coordinate(location.substring(location.lastIndexOf('!')+1));coords.put(location,p);
                        left=Math.min(left,p[0]);right=Math.max(right,p[0]);top=Math.min(top,p[1]);bottom=Math.max(bottom,p[1]);}
                    boundingCells+=(long)(right-left+1)*(bottom-top+1);
                    if(boundingCells>2000000)throw new IllegalArgumentException("bounding range limit");
                    XCellRange range=sheet.getCellRangeByPosition(left,top,right,bottom);
                    Object[][] data=UnoRuntime.queryInterface(XCellRangeData.class,range).getDataArray();
                    CellRangeAddress[] errors=UnoRuntime.queryInterface(XCellRangesQuery.class,range).queryFormulaCells(4).getRangeAddresses();
                    for(var item:coords.entrySet()){
                        int[] p=item.getValue();int code=0;String kind,value;
                        boolean isError=false;
                        for(CellRangeAddress r:errors)if(r.StartColumn<=p[0]&&p[0]<=r.EndColumn&&r.StartRow<=p[1]&&p[1]<=r.EndRow){isError=true;break;}
                        if(isError){XCell cell=sheet.getCellByPosition(p[0],p[1]);code=cell.getError();
                            if(code<=0)throw new IllegalStateException("error query mismatch");
                            kind="error";value=quoted(UnoRuntime.queryInterface(XTextRange.class,cell).getString());}
                        else{Object v=data[p[1]-top][p[0]-left];
                            if(v instanceof Number){double number=((Number)v).doubleValue();if(!Double.isFinite(number))throw new IllegalStateException("nonfinite value");kind="number";value=Double.toString(number);}
                            else if(v instanceof String){kind="string";value=quoted((String)v);}
                            else throw new IllegalStateException("unknown native scalar type");}
                        writer.write("["+quoted(item.getKey())+","+quoted(kind)+","+value+","+code+"]\n");count++;
                    }
                }
            }
            receipt.setProperty("cell_count",Integer.toString(count));receipt.setProperty("bounding_cells",Long.toString(boundingCells));
            receipt.setProperty("read_only","true");receipt.setProperty("saved","false");receipt.setProperty("calculated_all","true");
            receipt.setProperty("macro_execution","NEVER_EXECUTE");receipt.setProperty("external_link_updates","NO_UPDATE");
            receipt.setProperty("status","pass");exit=0;
        }catch(Exception error){receipt.setProperty("status","evaluator_error");receipt.setProperty("error",error.toString());}
        finally{
            if(component!=null)try{UnoRuntime.queryInterface(XCloseable.class,component).close(true);}catch(Exception ignored){}
            if(desktop!=null)try{desktop.terminate();}catch(Exception ignored){}
            try(var writer=Files.newBufferedWriter(Path.of(args[2]),StandardCharsets.UTF_8)){receipt.store(writer,"native Calc bulk values");}
        }
        System.exit(exit);
    }
}
