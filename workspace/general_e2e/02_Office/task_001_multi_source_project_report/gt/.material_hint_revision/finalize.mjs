import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const work=path.dirname(fileURLToPath(import.meta.url));
const skill='C:/Users/congzhang22/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations';
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
await fs.mkdir(path.join(work,'final'),{recursive:true});
const result=await finalizePresentation({
 workspaceDir:work,
 candidatePath:path.join(work,'draft','05_阶段汇报_v1.0.pptx'),
 finalPath:path.join(work,'final','05_阶段汇报_v1.0.pptx'),
 pythonExecutable:'C:/Users/congzhang22/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 explicitTotalSlideCount:24,
 requiredNativeTableOwnerSlides:Array.from({length:12},(_,i)=>i*2+1),
 requiredNativeChartOwnerSlides:[],
 layoutArgs:['--validate-bullet-geometry','--validate-heading-fit',...Array.from({length:12},(_,i)=>['--require-native-table-slide',String(i*2+1)]).flat()],
 verifyArtifactToolImport:true,
 receiptPath:path.join(work,'presentation_validation.json')
});
console.log(JSON.stringify({finalPath:result.finalPath,receiptPath:result.receiptPath}));
