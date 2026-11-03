"""Index every pinned native source; bound excerpts rather than the stored corpus."""
import hashlib
from itertools import islice
import json
import re
from uuid import UUID

from app.tenders.policy import DomainError
from app.tenders.repository import Repository


def canonical_extraction(document):
    anchors=[]
    prefix=document["document_version_id"]+"-"
    for anchor in document["anchors"]:
        if not anchor["anchor_id"].startswith(prefix) or anchor["document_version_id"]!=document["document_version_id"]:
            raise DomainError(422,"INVALID_EXTRACTION","Native anchor identity does not match its source.")
        anchors.append({"key":anchor["anchor_id"][len(prefix):],"text":anchor["text"],
            "metadata":{k:v for k,v in anchor.items() if k not in ("anchor_id","document_version_id","source_role","text")}})
    value={"anchors":anchors,"locations":document["locations"],"status":document["status"]}
    return value,hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def coverage(inventory,source_complete=True,source_error=None):
    gaps=[]
    for document in inventory:
        locations=[loc for loc in document["locations"] if loc["status"]!="complete"]
        if document["status"]!="complete" and not locations:
            locations=[{"status":document["status"],"location_label":"Document coverage"}]
        for location in locations:
            gaps.append({"document_version_id":document["document_version_id"],"filename":document["filename"],
                         **location,"materiality":"unknown"})
    if source_error or (not source_complete and not gaps):
        gaps.append({"document_version_id":None,"filename":None,"status":"partial",
                     "location_label":"Pack coverage","error_code":source_error or "SOURCE_INCOMPLETE","materiality":"unknown"})
    return {"complete":bool(inventory) and source_complete and not gaps,"gaps":gaps,"source_count":len(inventory)}


class SourceIndex:
    def __init__(self,pool):
        self.pool=pool

    async def index_sources(self,actor_scope,parsed_sources_version_id,parser_version):
        actor=actor_scope
        async with self.pool.acquire() as c,c.transaction():
            await Repository(self.pool)._member(c,actor)
            artifact=await c.fetchrow("""
                SELECT a.* FROM m1_app.artifact_versions a JOIN m1_app.tenders t
                  ON t.workspace_id=a.workspace_id AND t.id=a.tender_id
                WHERE a.workspace_id=$1 AND a.id=$2 AND a.kind='parsed_sources' AND t.deleted_at IS NULL
            """,actor.workspace_id,UUID(str(parsed_sources_version_id)))
            if artifact is None: raise DomainError(404,"NOT_FOUND","Parsed source version not found.")
            parsed=json.loads(artifact["payload"]);manifest=json.loads(artifact["manifest"])
            if parsed.get("parser")!=parser_version:
                raise DomainError(409,"PARSER_VERSION_MISMATCH","Use the parser version recorded by the native artifact.")
            # Serialise index creation for a tender, without model calls or source downloads.
            tender=await c.fetchrow("SELECT input_revision FROM m1_app.tenders WHERE workspace_id=$1 AND id=$2 FOR UPDATE",
                                   actor.workspace_id,artifact["tender_id"])
            if tender["input_revision"]!=artifact["input_revision"]:
                raise DomainError(409,"STALE_SOURCE_INDEX","The parsed sources are no longer current.")
            existing=await c.fetchrow("""
                SELECT * FROM m1_app.source_index_versions WHERE workspace_id=$1
                  AND parsed_sources_version_id=$2 AND parser_version=$3
            """,actor.workspace_id,artifact["id"],parser_version)
            if existing: return {**dict(existing),"inventory":json.loads(existing["inventory"])}
            sources={s["id"]:s for s in manifest["documents"]}
            documents=parsed["documents"]
            if len(sources)!=len(manifest["documents"]) or len(documents)!=len(sources) or {d["document_version_id"] for d in documents}!=set(sources):
                raise DomainError(422,"INVALID_EXTRACTION","Parsed coverage must account for every pinned source exactly once.")
            ids=[UUID(key) for key in sources]
            rows=await c.fetch("""
                SELECT id,sha256,role FROM m1_app.document_versions
                WHERE workspace_id=$1 AND tender_id=$2 AND id=ANY($3::uuid[])
                UNION ALL
                SELECT id,payload->'document'->>'sha256' AS sha256,'company_evidence' AS role
                FROM m1_app.artifact_versions
                WHERE workspace_id=$1 AND kind='company_evidence' AND id=ANY($3::uuid[])
            """,actor.workspace_id,artifact["tender_id"],ids)
            authoritative={str(r["id"]):r for r in rows}
            inventory=[];mappings=[];seen={}
            source_order={d["document_version_id"]:i for i,d in enumerate(documents)}
            # Shared caches must be acquired in one order across concurrent tenders.
            for document in sorted(documents,key=lambda d:d["sha256"]):
                key=document["document_version_id"];source=sources[key];original=authoritative.get(key)
                if original is None or source["sha256"]!=original["sha256"] or document["sha256"]!=original["sha256"] or source["role"]!=original["role"] or document["source_role"]!=original["role"]:
                    raise DomainError(422,"SOURCE_SCOPE_MISMATCH","Index sources must match their immutable workspace versions.")
                inventory.append({"document_version_id":key,"filename":source["filename"],"sha256":source["sha256"],
                    "status":document["status"],"locations":document["locations"],"duplicate_of":seen.get(source["sha256"])})
                seen.setdefault(source["sha256"],key)
                if document["status"]=="failed":
                    continue
                canonical,digest=canonical_extraction(document)
                extraction=await c.fetchrow("""
                    INSERT INTO m1_app.source_extractions(workspace_id,sha256,parser_version,extraction_sha256,status,locations,anchor_count)
                    VALUES($1,$2,$3,$4,$5,$6::jsonb,$7) ON CONFLICT(workspace_id,sha256,parser_version) DO NOTHING RETURNING *
                """,actor.workspace_id,source["sha256"],parser_version,digest,document["status"],json.dumps(document["locations"]),len(document["anchors"]))
                if extraction:
                    entries=[]
                    for anchor in canonical["anchors"]:
                        # Overlap preserves boundary clauses and avoids PostgreSQL's tsvector size limit.
                        for start in range(0,len(anchor["text"]),5488):
                            entries.append((actor.workspace_id,extraction["id"],len(entries),anchor["key"],
                                json.dumps({**anchor["metadata"],"character_start":start}),anchor["text"][start:start+6000]))
                    if entries:
                        await c.executemany("""
                            INSERT INTO m1_app.source_extraction_anchors(workspace_id,extraction_id,ordinal,anchor_key,metadata,text)
                            VALUES($1,$2,$3,$4,$5::jsonb,$6)
                        """,entries)
                else:
                    extraction=await c.fetchrow("SELECT * FROM m1_app.source_extractions WHERE workspace_id=$1 AND sha256=$2 AND parser_version=$3",
                                                actor.workspace_id,source["sha256"],parser_version)
                    if extraction["extraction_sha256"]!=digest:
                        raise DomainError(409,"EXTRACTION_CONFLICT","Identical bytes/parser produced conflicting extraction; preserve and investigate both artifacts.")
                mappings.append((actor.workspace_id,UUID(key),extraction["id"],source["filename"],source["role"]))
            inventory.sort(key=lambda d:source_order[d["document_version_id"]])
            row=await c.fetchrow("""
                INSERT INTO m1_app.source_index_versions(workspace_id,tender_id,parsed_sources_version_id,input_revision,parser_version,inventory)
                VALUES($1,$2,$3,$4,$5,$6::jsonb) RETURNING *
            """,actor.workspace_id,artifact["tender_id"],artifact["id"],artifact["input_revision"],parser_version,json.dumps(inventory))
            await c.executemany("""
                INSERT INTO m1_app.source_index_documents(workspace_id,index_id,document_version_id,extraction_id,filename,source_role)
                VALUES($1,$2,$3,$4,$5,$6)
            """,[(workspace,row["id"],*rest) for workspace,*rest in mappings])
            return {**dict(row),"inventory":inventory}

    async def _load(self,c,index_id,actor):
        await Repository(self.pool)._member(c,actor)
        row=await c.fetchrow("""
            SELECT i.*,t.input_revision AS current_revision,
                   a.payload->>'complete'='true' AS source_complete,a.payload->>'error_code' AS source_error
            FROM m1_app.source_index_versions i
            JOIN m1_app.tenders t ON t.workspace_id=i.workspace_id AND t.id=i.tender_id
            JOIN m1_app.artifact_versions a ON a.workspace_id=i.workspace_id AND a.id=i.parsed_sources_version_id
            WHERE i.workspace_id=$1 AND i.id=$2 AND t.deleted_at IS NULL
        """,actor.workspace_id,UUID(str(index_id)))
        if row is None: raise DomainError(404,"NOT_FOUND","Source index not found.")
        if row["input_revision"]!=row["current_revision"]:
            raise DomainError(409,"STALE_SOURCE_INDEX","Sources changed; retrieve from a current index.")
        return row

    async def retrieve(self,query,source_index_version,actor_scope,token_limit):
        if not isinstance(query,str) or not query.strip() or len(query)>512 or type(token_limit) is not int or not 256<=token_limit<=32768:
            raise DomainError(422,"INVALID_RETRIEVAL","Provide a bounded query and excerpt allowance between 256 and 32768 tokens.")
        async with self.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
            row=await self._load(c,source_index_version,actor_scope)
            matches=await c.fetch("""
                SELECT d.document_version_id,d.filename,d.source_role,a.anchor_key,a.metadata,a.text
                FROM m1_app.source_index_documents d
                JOIN m1_app.source_extraction_anchors a ON a.workspace_id=d.workspace_id AND a.extraction_id=d.extraction_id
                WHERE d.workspace_id=$1 AND d.index_id=$2 AND a.search @@ websearch_to_tsquery('simple',$3)
                ORDER BY ts_rank_cd(a.search,websearch_to_tsquery('simple',$3)) DESC,d.document_version_id,a.ordinal LIMIT 65
            """,actor_scope.workspace_id,row["id"],query)
            excerpts=[];truncated=len(matches)>64;used=set()
            for match in matches[:64]:
                key=(match["document_version_id"],match["anchor_key"])
                if key in used: truncated=True;continue
                metadata=json.loads(match["metadata"])
                base={"source_index_version":str(row["id"]),"document_version_id":str(match["document_version_id"]),
                    "anchor_id":str(match["document_version_id"])+"-"+match["anchor_key"],"filename":match["filename"],
                    "source_role":match["source_role"],**metadata,"quote":""}
                room=token_limit-len(json.dumps(excerpts+[base],ensure_ascii=False).encode())
                if room<=0: truncated=True;break
                text=match["text"];terms=re.findall(r"\w+",query.casefold())
                positions=[text.casefold().find(t) for t in terms if t not in ("or","and","not") and text.casefold().find(t)>=0]
                hit=min(positions,default=0);start=max(0,hit-min(160,room//4))
                quote=text[start:start+room]
                base["character_start"]=metadata.get("character_start",0)+start
                while quote and len(json.dumps(excerpts+[{**base,"quote":quote}],ensure_ascii=False).encode())>token_limit:
                    quote=quote[:-max(1,len(quote)//8)]
                if not quote: truncated=True;break
                excerpts.append({**base,"quote":quote})
                used.add(key);truncated|=start>0 or start+len(quote)<len(text)
            return {"source_index_version":str(row["id"]),"excerpts":excerpts,
                    "coverage":coverage(json.loads(row["inventory"]),row["source_complete"],row["source_error"]),"truncated":truncated}

    async def retrieve_overview(self,source_index_version,actor_scope):
        # Labelled native passages supplement (and never replace) the critical retrieval allowance.
        patterns=[r"tender[\s\n]+ref(?:erence)?[^\n]{0,35}[0-9]|buyer[\s\n]*:|contracting authority",
            r"contract[\s\n]+period|duration[\s\n]+of[\s\n]+(?:[a-z-]+[\s\n]+)?\(?[0-9]+",
            r"(?:sites|installations)[^\n.]{0,80}(?:as follows|are listed)|following[\s\n]+(sites|installations)|(?:^|\n)sites[\s\n]*(?::|and[\s\n]+installations[\s\n]*(?:\n|:))"]
        batches=[]
        async with self.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
            index=await self._load(c,source_index_version,actor_scope)
            for pattern in patterns:
                matches=await c.fetch("""SELECT d.document_version_id,d.filename,d.source_role,a.anchor_key,a.metadata,a.text
                    FROM m1_app.source_index_documents d
                    JOIN m1_app.source_extraction_anchors a ON a.workspace_id=d.workspace_id AND a.extraction_id=d.extraction_id
                    WHERE d.workspace_id=$1 AND d.index_id=$2 AND d.source_role IN ('tender','addendum') AND a.text ~* $3
                    ORDER BY CASE WHEN a.text ~* $4 THEN 0 ELSE 1 END,length(a.text),d.document_version_id,a.ordinal LIMIT 24""",
                    actor_scope.workspace_id,index["id"],pattern,
                    r"board|agency|ministry|council|authority" if not batches else r"CONTRACT[\s\n]+PERIOD|duration[\s\n]+of" if len(batches)==1 else r"as follows")
                candidates=[]
                for match in matches:
                    for hit in islice(re.finditer(pattern,match["text"],re.I),8):
                        duration=re.search(r"(?:\d+\)?|one|two|three|four|five|six|seven|eight|nine|ten)[\s\n]+(?:months?|years?)",match["text"][hit.start():hit.start()+500],re.I)
                        if len(batches)==1 and (not duration or duration.start()>160): continue
                        identity=len(batches)==0 and bool(re.search(r"board|agency|ministry|council|authority",match["text"],re.I))
                        priority=(not identity if len(batches)==0 else
                            (0 if hit.group().isupper() else 1 if hit.group().lower().startswith("duration") else 2)
                            if len(batches)==1 else (0 if "as follows" in hit.group().lower() else 1))
                        absolute=json.loads(match["metadata"]).get("character_start",0)+hit.start()
                        candidates.append((priority,absolute,hit.start(),match))
                batches.append(sorted(candidates,key=lambda m:(m[0],m[1])))
        selected=[];seen=set();terms=set()
        # Reserve space for identity, named sites/transition and two different term passages.
        for facet,allowance in ((0,1050),(2,2000),(1,975),(1,975)):
            for _,absolute,position,match in batches[facet]:
                key=(facet,match["document_version_id"],match["anchor_key"],absolute)
                if key in seen: continue
                metadata=json.loads(match["metadata"]);text=match["text"]
                term=re.search(r"(?:\d+\)?|one|two|three|four|five|six|seven|eight|nine|ten)[\s\n]+(?:months?|years?)",text[position:position+500],re.I) if facet==1 else None
                if term and term.group().casefold() in terms: continue
                start=max(0,position-(220 if facet==0 else 100))
                base={"source_index_version":str(index["id"]),"document_version_id":str(match["document_version_id"]),
                    "anchor_id":str(match["document_version_id"])+"-"+match["anchor_key"],"filename":match["filename"],
                    "source_role":match["source_role"],**metadata,"character_start":metadata.get("character_start",0)+start,"quote":""}
                limit=min(5000,len(json.dumps(selected,ensure_ascii=False).encode())+allowance)
                quote=text[start:start+allowance]
                while quote and len(json.dumps(selected+[{**base,"quote":quote}],ensure_ascii=False).encode())>limit:
                    quote=quote[:-max(1,len(quote)//20)]
                if not quote: break
                selected.append({**base,"quote":quote});seen.add(key)
                if term: terms.add(term.group().casefold())
                break
        return selected

    async def validate_excerpt(self,actor,excerpt):
        async with self.pool.acquire() as c,c.transaction(isolation="repeatable_read"):
            index=await self._load(c,excerpt["source_index_version"],actor)
            rows=await c.fetch("""
                SELECT a.text FROM m1_app.source_index_documents d
                JOIN m1_app.source_extraction_anchors a ON a.workspace_id=d.workspace_id AND a.extraction_id=d.extraction_id
                WHERE d.workspace_id=$1 AND d.index_id=$2 AND d.document_version_id=$3
                  AND $4=d.document_version_id::text || '-' || a.anchor_key
            """,actor.workspace_id,index["id"],UUID(excerpt["document_version_id"]),excerpt["anchor_id"])
            if not excerpt.get("quote") or not any(excerpt["quote"] in r["text"] for r in rows):
                raise DomainError(422,"INVALID_EXCERPT","The exact excerpt must occur in its pinned native source.")
            return dict(index)
