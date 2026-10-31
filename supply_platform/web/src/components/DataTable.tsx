import { useState, type ChangeEvent, type ReactNode } from "react";
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from "@mui/material";

/** 表格列定义。render 优先级高于按 id 取字段。 */
export interface Column<T> {
  id: string;
  label: string;
  align?: "left" | "right" | "center";
  render?: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  /** 行唯一键。 */
  rowKey: (row: T) => string | number;
  /** 默认每页行数。 */
  pageSize?: number;
  /** 空数据文案。 */
  emptyText?: string;
}

/**
 * 通用数据表格：内置客户端分页（每页 5/10/25/50）。
 * 筛选逻辑由调用方在取数时完成（如 Leads 页按 state/tier 请求后端）。
 */
export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  pageSize = 10,
  emptyText = "暂无数据",
}: DataTableProps<T>) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(pageSize);

  const handleChangePage = (_event: unknown, newPage: number) => setPage(newPage);

  const handleChangeRowsPerPage = (event: ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const pagedRows = rows.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            {columns.map((col) => (
              <TableCell key={col.id} align={col.align ?? "left"} sx={{ fontWeight: 700 }}>
                {col.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {pagedRows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} align="center">
                <Box sx={{ py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    {emptyText}
                  </Typography>
                </Box>
              </TableCell>
            </TableRow>
          ) : (
            pagedRows.map((row) => (
              <TableRow key={rowKey(row)} hover>
                {columns.map((col) => (
                  <TableCell key={col.id} align={col.align ?? "left"}>
                    {col.render
                      ? col.render(row)
                      : (row as Record<string, ReactNode>)[col.id]}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      <TablePagination
        rowsPerPageOptions={[5, 10, 25, 50]}
        component="div"
        count={rows.length}
        rowsPerPage={rowsPerPage}
        page={page}
        onPageChange={handleChangePage}
        onRowsPerPageChange={handleChangeRowsPerPage}
        labelRowsPerPage="每页"
        labelDisplayedRows={({ from, to, count }) => `${from}–${to} / 共 ${count}`}
      />
    </TableContainer>
  );
}
