# Database Export/Import — Client Implementation Guide

## Overview

Two new endpoints allow the client to:
1. **Export** the entire database state as JSON (backup)
2. **Import** a previously exported JSON state (restore)

This enables:
- Creating backups for safekeeping
- Transferring data between devices
- Syncing state with other users/instances
- Testing and development (quick restore to known states)

---

## Server Endpoints

### 1. Export Database

**Endpoint:** `GET /api/admin/export-database`  
**Method:** GET  
**Auth:** None (currently)  
**Body:** None  
**Response:** 200 OK with JSON body

**Response Format:**
```json
{
  "version": "1.0",
  "exported_at": "2026-05-06T12:34:56.789+00:00",
  "accounts": [
    {
      "id": "a1",
      "name": "Main Checking",
      "type": "checking",
      "balance": 4823.67,
      "available_balance": 4823.67,
      "institution_name": "Chase Bank",
      "color": "#2196F3",
      "created_at": "2026-05-06T10:00:00+00:00",
      "updated_at": null
    },
    ...
  ],
  "transactions": [
    {
      "id": "t1",
      "title": "Monthly Salary",
      "original_description": "PAYROLL DEPOSIT",
      "merchant_name": null,
      "provider_transaction_id": "12345",
      "amount": 5200.0,
      "type": "income",
      "category": "Paychecks",
      "provider_category": null,
      "date": "2026-05-06T12:00:00+00:00",
      "pending": false,
      "account_id": "a1",
      "notes": null,
      "created_at": "2026-05-06T10:00:00+00:00",
      "updated_at": null
    },
    ...
  ],
  "budgets": [
    {
      "id": "b1",
      "category": "Groceries",
      "allocated": 400.0,
      "color": "#66BB6A",
      "created_at": "2026-05-06T10:00:00+00:00",
      "updated_at": null
    },
    ...
  ],
  "account_snapshots": [
    {
      "id": 1,
      "user_id": 1,
      "snapshot_date": "2026-05-06",
      "net_worth": 45671.17,
      "total_assets": 46918.67,
      "total_liabilities": 1247.5,
      "created_at": "2026-05-06T10:00:00+00:00"
    },
    ...
  ],
  "simplefin_config": {
    "id": 1,
    "access_url_encrypted": "...",
    "institutions": ["Chase Bank", "Ally Bank"],
    "last_synced_at": "2026-05-06T12:00:00+00:00",
    "created_at": "2026-05-06T10:00:00+00:00",
    "updated_at": null
  }
}
```

**Usage:**
```bash
curl http://localhost:8000/api/admin/export-database > backup_2026-05-06.json
```

---

### 2. Import Database

**Endpoint:** `POST /api/admin/import-database`  
**Method:** POST  
**Auth:** None (currently)  
**Body:** JSON with the structure below

**Request Format:**
```json
{
  "accounts": [...],
  "transactions": [...],
  "budgets": [...],
  "account_snapshots": [...],
  "simplefin_config": {...}
}
```

You can send a subset — any missing tables will just be imported as empty.

**Response (200 OK):**
```json
{
  "ok": true,
  "message": "Database import complete.",
  "imported_records": {
    "accounts": 5,
    "transactions": 42,
    "budgets": 7,
    "account_snapshots": 31,
    "simplefin_config": 1
  }
}
```

**Error Response (400 Bad Request):**
```json
{
  "detail": "Import failed: <error details>"
}
```

**Usage:**
```bash
curl -X POST http://localhost:8000/api/admin/import-database \
  -H "Content-Type: application/json" \
  -d @backup_2026-05-06.json
```

---

## Client Implementation

### Dart/Flutter Implementation

#### 1. Export Backup

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';

Future<File> exportDatabase(String serverUrl) async {
  try {
    final response = await http.get(
      Uri.parse('$serverUrl/api/admin/export-database'),
    );

    if (response.statusCode != 200) {
      throw Exception('Export failed: ${response.statusCode}');
    }

    final jsonData = response.body; // Already JSON string

    // Save to device storage with timestamp
    final directory = await getApplicationDocumentsDirectory();
    final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('${directory.path}/finora_backup_$timestamp.json');

    await file.writeAsString(jsonData);
    return file;

  } catch (e) {
    throw Exception('Failed to export database: $e');
  }
}
```

#### 2. Import from File

```dart
Future<bool> importDatabase(String serverUrl, File backupFile) async {
  try {
    final jsonString = await backupFile.readAsString();
    final jsonData = jsonDecode(jsonString);

    final response = await http.post(
      Uri.parse('$serverUrl/api/admin/import-database'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(jsonData),
    );

    if (response.statusCode == 200) {
      final result = jsonDecode(response.body);
      print('Import successful: ${result["message"]}');
      print('Imported: ${result["imported_records"]}');
      return true;
    } else {
      final error = jsonDecode(response.body);
      throw Exception('Import failed: ${error["detail"]}');
    }

  } catch (e) {
    throw Exception('Failed to import database: $e');
  }
}
```

#### 3. UI Integration Example

```dart
class BackupSettingsPage extends StatefulWidget {
  @override
  State<BackupSettingsPage> createState() => _BackupSettingsPageState();
}

class _BackupSettingsPageState extends State<BackupSettingsPage> {
  bool _isExporting = false;
  bool _isImporting = false;

  Future<void> _handleExport() async {
    setState(() => _isExporting = true);
    try {
      final file = await exportDatabase('http://localhost:8000');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Backup saved to: ${file.path}')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Export failed: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      setState(() => _isExporting = false);
    }
  }

  Future<void> _handleImport() async {
    // Show file picker
    final FilePicker picker = FilePicker.platform;
    final result = await picker.pickFiles(type: FileType.any);

    if (result != null && result.files.isNotEmpty) {
      final file = File(result.files.first.path!);

      setState(() => _isImporting = true);
      try {
        final success = await importDatabase('http://localhost:8000', file);
        if (success && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Database imported successfully!')),
          );
          // Optionally refresh the UI:
          // ref.refresh(transactionsProvider);
          // ref.refresh(accountsProvider);
          // etc.
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Import failed: $e'), backgroundColor: Colors.red),
          );
        }
      } finally {
        setState(() => _isImporting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Backup & Restore')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ElevatedButton.icon(
              onPressed: _isExporting ? null : _handleExport,
              icon: const Icon(Icons.download),
              label: _isExporting ? const Text('Exporting...') : const Text('Export Backup'),
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: _isImporting ? null : _handleImport,
              icon: const Icon(Icons.upload),
              label: _isImporting ? const Text('Importing...') : const Text('Import Backup'),
            ),
          ],
        ),
      ),
    );
  }
}
```

#### 4. Riverpod Integration (Optional)

If using Riverpod providers for state:

```dart
final databaseExportProvider = FutureProvider.autoDispose<File>((ref) async {
  return await exportDatabase('http://localhost:8000');
});

Future<void> refreshAllProviders(WidgetRef ref) {
  ref.refresh(transactionsProvider);
  ref.refresh(accountsProvider);
  ref.refresh(budgetsProvider);
  ref.refresh(accountSnapshotProvider);
  // etc.
}
```

---

## Workflow Example

1. **User navigates to Settings → Backup & Restore**
2. **Click "Export Backup"**
   - Client calls `GET /api/admin/export-database`
   - Saves JSON to device file system (with timestamp)
   - Shows success message with file path
3. **User can share the file** (email, cloud sync, etc.)
4. **To restore on another device:**
   - User picks the backup file
   - Client calls `POST /api/admin/import-database` with the file
   - Server deletes all data, then imports from the file
   - Client refreshes all Riverpod providers to update UI
   - Shows success message

---

## Important Notes

### Before Importing:
- Show a confirmation dialog: **"This will replace all local data. Continue?"**
- Mention what will be deleted (accounts, transactions, budgets, etc.)

### After Importing:
- **Refresh all provider state** so the UI reflects the imported data
- Show a success toast/snackbar
- Consider navigating the user back to the Dashboard

### File Handling:
- Save exported backups with a **timestamp** in the filename (e.g., `finora_backup_2026-05-06T12-34-56.json`)
- Use `path_provider` or similar to store in the app's documents directory
- Consider compressing larger backups with gzip if needed

### Error Handling:
- Network errors (no connection to server)
- File read/write errors (permissions, storage full)
- JSON parsing errors (corrupted backup file)
- Server-side validation errors (mismatched schema)

---

## Optional Enhancements

1. **Encryption**: Encrypt the backup file with a password before sharing
2. **Cloud Sync**: Auto-upload backups to cloud storage (Google Drive, iCloud, Dropbox)
3. **Scheduled Exports**: Periodic automatic backups
4. **Diff/Merge**: Show what will be imported before committing
5. **Compression**: Gzip the JSON for smaller file sizes
