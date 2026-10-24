package com.autoquestion.mobile;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileNotFoundException;

/** One fixed, read-only, verified-cache APK. No directory or arbitrary path exposure. */
public final class UpdatePackageProvider extends ContentProvider {
    static Uri uri(android.content.Context context) {
        return new Uri.Builder().scheme("content").authority(context.getPackageName() + ".updates")
                .path("/apk/AutoQuestion.apk").build();
    }
    @Override public boolean onCreate() { return true; }
    private File file(Uri uri) throws FileNotFoundException {
        if (getContext() == null || !uri(getContext()).equals(uri)) throw new FileNotFoundException("无此更新文件");
        File file = UpdateManager.readyFile(getContext());
        try {
            File directory = new File(getContext().getCacheDir().getCanonicalFile(), "updates");
            File expected = new File(directory, "AutoQuestion.apk");
            if (!file.isFile() || !file.getCanonicalFile().equals(expected)) throw new FileNotFoundException("更新不可用");
        } catch (java.io.IOException error) { throw new FileNotFoundException("更新不可用"); }
        return file;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("只允许读取更新包");
        return ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public String getType(Uri uri) {
        if (getContext() == null || !uri(getContext()).equals(uri)) throw new IllegalArgumentException("无此更新文件");
        return "application/vnd.android.package-archive";
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] selectionArgs, String sortOrder) {
        try {
            File file = file(uri);
            String[] columns = projection == null ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE} : projection;
            MatrixCursor cursor = new MatrixCursor(columns); Object[] row = new Object[columns.length];
            for (int i = 0; i < columns.length; i++) {
                if (OpenableColumns.DISPLAY_NAME.equals(columns[i])) row[i] = "AutoQuestion-update.apk";
                else if (OpenableColumns.SIZE.equals(columns[i])) row[i] = file.length();
            }
            cursor.addRow(row); return cursor;
        } catch (FileNotFoundException error) { return null; }
    }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException("只读"); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException("只读"); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException("只读"); }
}
