package za.co.topprivateplug;

import android.content.*;
import android.database.*;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import java.io.*;

/** Only Android's installer receives a temporary read grant for this fixed file. */
public final class UpdateProvider extends ContentProvider {
    @Override public boolean onCreate(){return true;}
    private File target(Uri uri)throws FileNotFoundException{if(!"/pilot.apk".equals(uri.getPath()))throw new FileNotFoundException();return new File(getContext().getFilesDir(),"updates/pilot.apk");}
    @Override public String getType(Uri uri){return "application/vnd.android.package-archive";}
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode)throws FileNotFoundException{if(!"r".equals(mode))throw new FileNotFoundException();return ParcelFileDescriptor.open(target(uri),ParcelFileDescriptor.MODE_READ_ONLY);}
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String sort){try{File f=target(uri);String[] columns=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;MatrixCursor result=new MatrixCursor(columns);Object[] values=new Object[columns.length];for(int i=0;i<columns.length;i++)values[i]=OpenableColumns.DISPLAY_NAME.equals(columns[i])?"Top-private-Plug-update.apk":OpenableColumns.SIZE.equals(columns[i])?f.length():null;result.addRow(values);return result;}catch(Exception e){return null;}}
    @Override public Uri insert(Uri u,ContentValues v){throw new UnsupportedOperationException();}
    @Override public int update(Uri u,ContentValues v,String s,String[] a){throw new UnsupportedOperationException();}
    @Override public int delete(Uri u,String s,String[] a){throw new UnsupportedOperationException();}
}
