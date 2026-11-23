"""Offline HTML extraction; tables keep merged headers and row provenance."""
import re
from bs4 import BeautifulSoup
EXTRACTOR_VERSION='6'
BLOCKS=['h1','h2','h3','h4','h5','h6','p','li','table','dl','pre','div','blockquote']

def own_inline_text(node):
    parts=[]
    def visit(parent):
        for child in parent.children:
            if getattr(child,'name',None) is None:parts.append(str(child))
            elif child.name not in BLOCKS:visit(child)
    visit(node)
    return re.sub(r'\s+',' ',' '.join(parts)).strip()

def clean_text(node):return re.sub(r'\s+',' ',node.get_text(' ',strip=True)).strip()

def expand_table(table,variant=None,choices=()):
    pending={};rows=[]
    for tr in table.find_all('tr'):
        if tr.find_parent('table') is not table:continue
        grid={};next_pending={}
        for column,(value,left) in pending.items():
            grid[column]=value
            if left>1:next_pending[column]=(value,left-1)
        column=0;cells=tr.find_all(['td','th'],recursive=False)
        if variant:
            cells=[cell for cell in cells if not (set(cell.get('class',[]))&set(choices)) or variant in cell.get('class',[])]
        for cell in cells:
            while column in grid:column+=1
            try:colspan=min(128,max(1,int(cell.get('colspan',1))));rowspan=min(1000,max(1,int(cell.get('rowspan',1))))
            except (ValueError,TypeError):colspan=rowspan=1
            if variant or cell.find('table') is not None:
                strings=[]
                for string in cell.find_all(string=True):
                    node=string.parent
                    if node.find_parent('table') is not table:continue
                    if any(set(parent.get('class',[]))&set(choices) and variant not in parent.get('class',[]) for parent in [node]+list(node.parents) if parent is not cell and parent is not table):continue
                    strings.append(str(string))
                value=re.sub(r'\s+',' ',' '.join(strings)).strip()
            else:value=clean_text(cell)
            for offset in range(colspan):
                grid[column+offset]=value
                if rowspan>1:next_pending[column+offset]=(value,rowspan-1)
            column+=colspan
        if grid:rows.append({'values':[grid.get(c,'') for c in range(max(grid)+1)],'header':bool(cells) and all(c.name=='th' for c in cells),'first_header':bool(cells) and cells[0].name=='th'})
        pending=next_pending
    return rows

def table_lines(table,labels=None):
    labels=labels or {}
    choices=set()
    for cell in table.select('td._toggle,th._toggle'):
        if cell.find_parent('table') is not table:continue
        choices.update(cls for cls in cell.get('class',[]) if cls in labels)
    if len(choices)>1:
        for variant in sorted(choices):
            for line in _table_lines(table,variant,choices):yield '计算方式='+labels[variant]+' | '+line
    else:yield from _table_lines(table)

def _table_lines(table,variant=None,choices=()):
    rows=expand_table(table,variant,choices);headers=[];started=False
    caption=table.find('caption',recursive=False)
    if caption:yield '表题：'+clean_text(caption)
    for number,row in enumerate(rows,1):
        values=row['values']
        if row['header'] and not started:
            while len(headers)<len(values):headers.append([])
            for index,value in enumerate(values):
                if value and value not in headers[index]:headers[index].append(value)
            continue
        started=True
        if len(values)==2 and row['first_header']:
            yield values[0]+'：'+values[1]
        else:
            labels=[' / '.join(headers[i]) if i<len(headers) and headers[i] else '列'+str(i+1) for i in range(len(values))]
            yield ' | '.join(label+'='+value for label,value in zip(labels,values) if value)
    if headers and (not started or not any(any(row['values']) for row in rows if not row['header'])):
        yield ' | '.join(' / '.join(values) for values in headers)

def extract_html(html,title,max_chars=1800):
    soup=BeautifulSoup(html,'lxml')
    root=soup.select_one('.mw-parser-output') or soup.select_one('#mw-content-text') or soup.select_one('article') or soup.body or soup
    for node in root.select('script,style,nav,.navbox,.vertical-navbox,.toc,.mw-editsection,.catlinks,.printfooter,.noprint,.mw-jump-link'):
        node.decompose()
    for image in list(root.find_all('img')):
        alt=image.get('alt','').strip()
        image.replace_with(alt if alt and len(alt)<80 and not re.search(r'\.(?:png|jpg|gif|svg|webp)$',alt,re.I) else '')
    labels={}
    for control in root.select('[class*="_toggler_show-"]'):
        label=clean_text(control)
        if not label or len(label)>120:continue
        for cls in control.get('class',[]):
            if cls.startswith('_toggler_show-'):
                labels.setdefault(cls[len('_toggler_show-'):],label)
    for explanation in root.select('.explain[title]'):
        for cls in explanation.parent.get('class',[]):
            if cls in labels:labels[cls]=clean_text(explanation)+'（'+explanation['title']+'）'
    owned_cache={}
    def context(node):
        values=[]
        for parent in reversed([node]+list(node.parents)):
            if parent is soup:continue
            if 'tabbertab' in parent.get('class',[]) and parent.get('title'):values.append(parent['title'])
            if parent.name in ('td','th') and parent.find('table') is not None:
                key=id(parent)
                if key not in owned_cache:
                    outer=parent.find_parent('table')
                    owned_cache[key]=' '.join(str(s).strip() for s in parent.find_all(string=True) if s.parent.find_parent('table') is outer).strip()
                owned=owned_cache[key]
                if owned and len(owned)<80 and owned not in values:values.append(owned)
            for cls in parent.get('class',[]):
                if cls in labels and labels[cls] not in values:values.append(labels[cls])
        return values
    result=[];headings=[];buffer=[];buffer_kind='text';buffer_section='';extra=[]
    def flush():
        nonlocal buffer
        if buffer:result.append({'kind':buffer_kind,'section':buffer_section,'text':'\n'.join(buffer)})
        buffer=[]
    def append(value,kind):
        nonlocal buffer_kind,buffer_section
        value=value.strip()
        if not value:return
        section=' / '.join([item[1] for item in headings]+extra)
        if kind!=buffer_kind or section!=buffer_section:flush()
        buffer_kind=kind;buffer_section=section
        for start in range(0,len(value),max_chars):
            part=value[start:start+max_chars]
            if sum(len(v)+1 for v in buffer)+len(part)>max_chars:flush()
            buffer.append(part)
    for node in [root]+root.find_all(BLOCKS):
        extra=context(node)
        if node.name=='table':
            flush()
            base_extra=extra
            for line in table_lines(node,labels):
                extra=base_extra+[line.split(' | ',1)[0]] if line.startswith('计算方式=') else base_extra
                append(line,'table')
            flush();continue
        if node.find_parent('table'):continue
        if node.find_parent(['li','dl','pre']):continue
        if node.name in ('div','blockquote','body'):
            append(own_inline_text(node),'text');continue
        if node.name.startswith('h'):
            value=clean_text(node)
            if not value or value==title:continue
            flush();level=int(node.name[1])
            while headings and headings[-1][0]>=level:headings.pop()
            headings.append((level,value));continue
        append(clean_text(node),'text')
    flush()
    return result
