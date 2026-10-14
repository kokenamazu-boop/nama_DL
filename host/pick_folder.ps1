$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NamaFolderPicker {
 [ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IFileDialog {
  [PreserveSig] int Show(IntPtr owner);
  void SetFileTypes(uint count, IntPtr types);
  void SetFileTypeIndex(uint index);
  void GetFileTypeIndex(out uint index);
  void Advise(IntPtr events, out uint cookie);
  void Unadvise(uint cookie);
  void SetOptions(uint options);
  void GetOptions(out uint options);
  void SetDefaultFolder(IShellItem item);
  void SetFolder(IShellItem item);
  void GetFolder(out IShellItem item);
  void GetCurrentSelection(out IShellItem item);
  void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
  void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
  void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
  void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
  void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
  void GetResult(out IShellItem item);
  void AddPlace(IShellItem item, uint location);
  void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string ext);
  void Close(int result);
  void SetClientGuid(ref Guid guid);
  void ClearClientData();
  void SetFilter(IntPtr filter);
 }
 [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IShellItem {
  void BindToHandler(IntPtr context, ref Guid handler, ref Guid iid, out IntPtr result);
  void GetParent(out IShellItem parent);
  void GetDisplayName(uint type, out IntPtr name);
  void GetAttributes(uint mask, out uint attributes);
  void Compare(IShellItem item, uint hint, out int order);
 }
 [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=false)]
 static extern void SHCreateItemFromParsingName(string path, IntPtr context, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out IShellItem item);
 public static string Pick(string initial, IntPtr owner) {
  object instance=Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")));
  IFileDialog dialog=(IFileDialog)instance;
  IShellItem folder=null, result=null;
  try {
   uint options; dialog.GetOptions(out options);
   dialog.SetOptions(options | 0x20u | 0x40u | 0x800u | 0x8u);
   dialog.SetTitle("nama_DL の保存先フォルダーを選択");
   dialog.SetOkButtonLabel("このフォルダーを選択");
   if (!String.IsNullOrEmpty(initial) && System.IO.Directory.Exists(initial)) {
    Guid iid=new Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE");
    SHCreateItemFromParsingName(initial, IntPtr.Zero, ref iid, out folder);
    dialog.SetFolder(folder);
   }
   int hr=dialog.Show(owner);
   if (hr==unchecked((int)0x800704C7)) return "";
   Marshal.ThrowExceptionForHR(hr);
   dialog.GetResult(out result);
   IntPtr name; result.GetDisplayName(0x80058000u, out name);
   try { return Marshal.PtrToStringUni(name); }
   finally { Marshal.FreeCoTaskMem(name); }
  } finally {
   if(result!=null) Marshal.ReleaseComObject(result);
   if(folder!=null) Marshal.ReleaseComObject(folder);
   Marshal.ReleaseComObject(instance);
  }
 }
}
'@
$owner = New-Object System.Windows.Forms.Form
try {
 $owner.TopMost = $true
 $owner.ShowInTaskbar = $false
 $owner.StartPosition = 'CenterScreen'
 $owner.Size = New-Object System.Drawing.Size(1,1)
 $owner.Opacity = 0
 $owner.Show()
 $owner.Activate()
 $selected = [NamaFolderPicker]::Pick($env:VIDEOBUTTON_FOLDER, $owner.Handle)
 @{path=$selected} | ConvertTo-Json -Compress
} finally { $owner.Dispose() }
