/* A deterministic native Writer API probe, never a semantic Judge.
 * Document macros and external-link updates are disabled on every load.
 * API: https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1frame_1_1XComponentLoader.html
 */
import com.sun.star.beans.PropertyState;
import com.sun.star.beans.PropertyValue;
import com.sun.star.bridge.XUnoUrlResolver;
import com.sun.star.comp.helper.Bootstrap;
import com.sun.star.container.XEnumeration;
import com.sun.star.container.XEnumerationAccess;
import com.sun.star.frame.XComponentLoader;
import com.sun.star.frame.XDesktop;
import com.sun.star.frame.XStorable;
import com.sun.star.lang.XComponent;
import com.sun.star.lang.XServiceInfo;
import com.sun.star.text.XText;
import com.sun.star.text.XTextCursor;
import com.sun.star.text.XTextDocument;
import com.sun.star.text.XTextRange;
import com.sun.star.text.XTextTable;
import com.sun.star.text.XTextTablesSupplier;
import com.sun.star.uno.UnoRuntime;
import com.sun.star.uno.XComponentContext;
import com.sun.star.util.XCloseable;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.regex.Pattern;

public class NativeDocxEditProbe {
    static final String BODY="EVAL_EDIT_BODY_20260922";
    static final String CELL="EVAL_EDIT_CELL_20260922";
    static final Pattern TASK=Pattern.compile("XQ-\\d{3}",
        Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE | Pattern.UNICODE_CHARACTER_CLASS);
    static PropertyValue value(String name,Object value) {
        return new PropertyValue(name,-1,value,PropertyState.DIRECT_VALUE);
    }
    static PropertyValue[] opening(boolean readonly) {
        return new PropertyValue[]{value("Hidden",true),value("ReadOnly",readonly),
            value("MacroExecutionMode",(short)0),value("UpdateDocMode",(short)0)};
    }
    static void close(XComponent doc) {
        if(doc!=null)try{UnoRuntime.queryInterface(XCloseable.class,doc).close(true);}catch(Exception ignored){}
    }
    static boolean paragraph(Object object) {
        XServiceInfo service=UnoRuntime.queryInterface(XServiceInfo.class,object);
        return service!=null && service.supportsService("com.sun.star.text.Paragraph");
    }
    static boolean nonempty(String text) {
        return text.codePoints().anyMatch(c->c!=0x85&&!Character.isWhitespace(c)&&!Character.isSpaceChar(c));
    }
    static int paragraphCount(XText text) throws Exception {
        int count=0;
        XEnumeration items=UnoRuntime.queryInterface(XEnumerationAccess.class,text).createEnumeration();
        while(items.hasMoreElements()) {
            Object item=items.nextElement();
            if(paragraph(item))count++;
            else {
                XTextTable table=UnoRuntime.queryInterface(XTextTable.class,item);
                if(table!=null)for(String name:table.getCellNames())
                    count+=paragraphCount(UnoRuntime.queryInterface(XText.class,table.getCellByName(name)));
            }
            if(count>100000)throw new IllegalStateException("Native paragraph observation exceeds resource budget");
        }
        return count;
    }
    static class Facts {
        int paragraphs;
        XTextRange body;
        String[] tableNames;
        List<Integer> requiredTables=new ArrayList<>();
    }
    static Facts inspect(XComponent document) throws Exception {
        Facts facts=new Facts();
        XTextDocument writer=UnoRuntime.queryInterface(XTextDocument.class,document);
        if(writer==null)throw new IllegalStateException("Loaded component is not a native text document");
        XEnumeration elements=UnoRuntime.queryInterface(XEnumerationAccess.class,writer.getText()).createEnumeration();
        while(elements.hasMoreElements()) {
            Object element=elements.nextElement();
            if(paragraph(element)) {
                facts.paragraphs++;
                XTextRange range=UnoRuntime.queryInterface(XTextRange.class,element);
                if(facts.body==null && facts.paragraphs>1 && nonempty(range.getString()))facts.body=range;
            } else {
                XTextTable table=UnoRuntime.queryInterface(XTextTable.class,element);
                if(table!=null)for(String name:table.getCellNames())
                    facts.paragraphs+=paragraphCount(UnoRuntime.queryInterface(XText.class,table.getCellByName(name)));
            }
            if(facts.paragraphs>100000)throw new IllegalStateException("Native paragraph observation exceeds resource budget");
        }
        var tables=UnoRuntime.queryInterface(XTextTablesSupplier.class,document).getTextTables();
        facts.tableNames=tables.getElementNames();
        for(int index=0;index<facts.tableNames.length;index++) {
            XTextTable table=UnoRuntime.queryInterface(XTextTable.class,tables.getByName(facts.tableNames[index]));
            StringBuilder text=new StringBuilder();
            for(String name:table.getCellNames())text.append(UnoRuntime.queryInterface(XText.class,table.getCellByName(name)).getString()).append('\n');
            if(TASK.matcher(text).find())facts.requiredTables.add(index);
        }
        return facts;
    }
    static XText cell(XComponent doc,String tableName) throws Exception {
        var tables=UnoRuntime.queryInterface(XTextTablesSupplier.class,doc).getTextTables();
        XTextTable table=UnoRuntime.queryInterface(XTextTable.class,tables.getByName(tableName));
        return UnoRuntime.queryInterface(XText.class,table.getCellByName("A2"));
    }
    public static void main(String[] args) throws Exception {
        // connection, known-good-control URI, original URI, editable-copy URI,
        // saved-copy URI, native-PDF URI, receipt path. All paths are owned by
        // the managed evaluator; the original and control are never saved.
        if(args.length!=7)throw new IllegalArgumentException("Expected seven native probe arguments");
        Properties receipt=new Properties();
        XDesktop desktop=null;XComponent control=null,document=null;
        int exit=2;
        try {
            receipt.setProperty("engine","LibreOffice Writer UNO");
            receipt.setProperty("document_macro_execution","NEVER_EXECUTE");
            receipt.setProperty("external_link_updates","NO_UPDATE");
            receipt.setProperty("phase","connect");
            XComponentContext local=Bootstrap.createInitialComponentContext((Map<String,Object>)null);
            XUnoUrlResolver resolver=UnoRuntime.queryInterface(XUnoUrlResolver.class,
                local.getServiceManager().createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver",local));
            Object remoteObject=null;
            for(int retry=0;retry<100;retry++) {
                try{remoteObject=resolver.resolve(args[0]);break;}
                catch(com.sun.star.connection.NoConnectException error){Thread.sleep(100);}
            }
            if(remoteObject==null)throw new IllegalStateException("Native UNO listener unavailable");
            XComponentContext remote=UnoRuntime.queryInterface(XComponentContext.class,remoteObject);
            Object service=remote.getServiceManager().createInstanceWithContext("com.sun.star.frame.Desktop",remote);
            desktop=UnoRuntime.queryInterface(XDesktop.class,service);
            XComponentLoader loader=UnoRuntime.queryInterface(XComponentLoader.class,service);
            receipt.setProperty("phase","control_open");
            control=loader.loadComponentFromURL(args[1],"_blank",0,opening(true));
            if(UnoRuntime.queryInterface(XTextDocument.class,control)==null)throw new IllegalStateException("Known-good control did not open as Writer");
            receipt.setProperty("control_opened","true");close(control);control=null;
            receipt.setProperty("phase","original_open_readonly");
            document=loader.loadComponentFromURL(args[2],"_blank",0,opening(true));
            if(UnoRuntime.queryInterface(XTextDocument.class,document)==null)
                throw new IllegalStateException("Candidate did not open as a native text document");
            receipt.setProperty("opened","true");
            receipt.setProperty("phase","original_inspection");
            Facts original=inspect(document);
            receipt.setProperty("native_paragraphs",Integer.toString(original.paragraphs));
            receipt.setProperty("native_tables",Integer.toString(original.tableNames.length));
            receipt.setProperty("required_tables",Integer.toString(original.requiredTables.size()));
            receipt.setProperty("phase","original_pdf_export");
            UnoRuntime.queryInterface(XStorable.class,document).storeToURL(args[5],
                new PropertyValue[]{value("FilterName","writer_pdf_Export"),value("Overwrite",true)});
            close(document);document=null;
            if(original.paragraphs<4 || original.tableNames.length<2 || original.body==null || original.requiredTables.size()<2) {
                receipt.setProperty("status","candidate_not_editable");
                receipt.setProperty("reason","candidate lacks editable body or two required tables");exit=0;
            } else {
                receipt.setProperty("phase","editable_copy_open");
                document=loader.loadComponentFromURL(args[3],"_blank",0,opening(false));
                Facts editable=inspect(document);
                if(editable.paragraphs!=original.paragraphs || editable.tableNames.length!=original.tableNames.length
                        || editable.requiredTables.size()!=original.requiredTables.size() || editable.body==null)
                    throw new IllegalStateException("Native editable copy view differs from original");
                receipt.setProperty("phase","native_body_edit");
                XTextDocument writer=UnoRuntime.queryInterface(XTextDocument.class,document);
                XTextCursor cursor=writer.getText().createTextCursorByRange(editable.body.getStart());
                writer.getText().insertString(cursor,BODY,false);
                receipt.setProperty("phase","native_table_edits");
                for(int index:editable.requiredTables) {
                    XText target=cell(document,editable.tableNames[index]);
                    XTextCursor position=target.createTextCursor();position.gotoStart(false);
                    target.insertString(position,CELL,false);
                }
                receipt.setProperty("phase","native_save");
                UnoRuntime.queryInterface(XStorable.class,document).storeAsURL(args[4],
                    new PropertyValue[]{value("FilterName","Office Open XML Text"),value("Overwrite",true)});
                close(document);document=null;
                receipt.setProperty("phase","native_reopen");
                document=loader.loadComponentFromURL(args[4],"_blank",0,opening(true));
                writer=UnoRuntime.queryInterface(XTextDocument.class,document);
                if(!writer.getText().getString().contains(BODY))throw new IllegalStateException("Native body edit did not persist");
                var after=UnoRuntime.queryInterface(XTextTablesSupplier.class,document).getTextTables();
                String[] names=after.getElementNames();
                for(int index:editable.requiredTables) {
                    if(index>=names.length || !cell(document,names[index]).getString().contains(CELL))
                        throw new IllegalStateException("Native required-table edit did not persist");
                }
                receipt.setProperty("body_persisted","true");
                receipt.setProperty("table_edits_persisted",Integer.toString(editable.requiredTables.size()));
                receipt.setProperty("status","pass");exit=0;
            }
        } catch(Throwable error) {
            if("original_open_readonly".equals(receipt.getProperty("phase"))
                    && "true".equals(receipt.getProperty("control_opened"))) {
                receipt.setProperty("status","candidate_not_openable");
                receipt.setProperty("reason","Candidate cannot open in the same native application that opened the known-good control");
                exit=0;
            } else receipt.setProperty("status","evaluator_error");
            receipt.setProperty("error",error.toString());error.printStackTrace();
        } finally {
            close(control);close(document);
            try(var stream=Files.newBufferedWriter(Path.of(args[6]),StandardCharsets.UTF_8)){receipt.store(stream,"Managed native Writer editability evidence");}
            if(desktop!=null)try{desktop.terminate();}catch(Exception ignored){}
        }
        System.exit(exit);
    }
}
